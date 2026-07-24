//! Authenticated, length-framed JSON-RPC client over a Unix domain socket.

use std::path::{Path, PathBuf};

use base64::{engine::general_purpose::STANDARD as BASE64, Engine as _};
use hmac::{Hmac, Mac};
use rand::RngCore;
use serde::de::DeserializeOwned;
use serde::Deserialize;
use serde_json::Value;
use sha2::Sha256;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::UnixStream;
use tokio::sync::Mutex;
use uuid::Uuid;
use zeroize::Zeroizing;

use crate::error::AppError;
use crate::rpc::protocol::{
    JsonRpcRequest, JsonRpcResponse, RpcMeta, MAX_FRAME_BYTES, PROTOCOL_VERSION,
};

type HmacSha256 = Hmac<Sha256>;

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct HandshakeResponse {
    ipc_session_id: Uuid,
    protocol_version: u32,
    profile_status: String,
    database_status: String,
    migration_version: String,
}

pub struct SidecarClient {
    socket_path: PathBuf,
    stream: Mutex<Option<UnixStream>>,
    ipc_session_id: Mutex<Option<Uuid>>,
    window_session_id: Uuid,
}

impl SidecarClient {
    pub fn new(socket_path: impl Into<PathBuf>) -> Self {
        Self {
            socket_path: socket_path.into(),
            stream: Mutex::new(None),
            ipc_session_id: Mutex::new(None),
            window_session_id: Uuid::new_v4(),
        }
    }

    pub fn socket_path(&self) -> &Path {
        &self.socket_path
    }

    pub async fn connect_and_handshake(
        &self,
        startup_token: Zeroizing<Vec<u8>>,
        app_version: &str,
        launch_id: Uuid,
    ) -> Result<(), AppError> {
        if startup_token.len() != 32 {
            return Err(AppError::Security(
                "IPC startup token must contain 32 bytes".to_owned(),
            ));
        }
        let stream = UnixStream::connect(&self.socket_path)
            .await
            .map_err(|error| AppError::Sidecar(format!("connect UDS: {error}")))?;
        *self.stream.lock().await = Some(stream);

        let mut nonce = [0_u8; 32];
        rand::thread_rng().fill_bytes(&mut nonce);
        let nonce_base64 = BASE64.encode(nonce);
        let mut mac = HmacSha256::new_from_slice(&startup_token)
            .map_err(|_| AppError::Security("invalid IPC token".to_owned()))?;
        mac.update(app_version.as_bytes());
        mac.update(PROTOCOL_VERSION.to_string().as_bytes());
        mac.update(launch_id.to_string().as_bytes());
        mac.update(nonce_base64.as_bytes());
        let proof = BASE64.encode(mac.finalize().into_bytes());
        let request = JsonRpcRequest::new(
            "system.handshake",
            serde_json::json!({
                "app_version": app_version,
                "protocol_version": PROTOCOL_VERSION,
                "launch_id": launch_id,
                "nonce": nonce_base64,
                "proof": proof,
            }),
            RpcMeta {
                trace_id: Uuid::new_v4(),
                ipc_session_id: None,
                window_session_id: self.window_session_id,
                idempotency_key: None,
            },
        );
        let response: HandshakeResponse = self.exchange(request).await?;
        if response.protocol_version != PROTOCOL_VERSION
            || response.profile_status != "ready"
            || response.database_status != "ready"
            || response.migration_version.is_empty()
        {
            self.disconnect().await;
            return Err(AppError::Sidecar(
                "Sidecar returned an invalid readiness contract".to_owned(),
            ));
        }
        *self.ipc_session_id.lock().await = Some(response.ipc_session_id);
        Ok(())
    }

    pub async fn call<T: DeserializeOwned>(
        &self,
        method: &str,
        params: Value,
        idempotency_key: Option<Uuid>,
    ) -> Result<T, AppError> {
        let session = (*self.ipc_session_id.lock().await)
            .ok_or_else(|| AppError::Sidecar("Sidecar profile is not open".to_owned()))?;
        let request = JsonRpcRequest::new(
            method,
            params,
            RpcMeta {
                trace_id: Uuid::new_v4(),
                ipc_session_id: Some(session),
                window_session_id: self.window_session_id,
                idempotency_key,
            },
        );
        self.exchange(request).await
    }

    pub async fn disconnect(&self) {
        *self.stream.lock().await = None;
        *self.ipc_session_id.lock().await = None;
    }

    async fn exchange<T: DeserializeOwned>(&self, request: JsonRpcRequest) -> Result<T, AppError> {
        let request_id = request.id.clone();
        let payload =
            serde_json::to_vec(&request).map_err(|error| AppError::Internal(error.to_string()))?;
        if payload.is_empty() || payload.len() > MAX_FRAME_BYTES {
            return Err(AppError::Validation(
                "RPC request exceeds frame limit".to_owned(),
            ));
        }
        let mut guard = self.stream.lock().await;
        let stream = guard
            .as_mut()
            .ok_or_else(|| AppError::Sidecar("Sidecar is disconnected".to_owned()))?;
        stream
            .write_all(&(payload.len() as u32).to_be_bytes())
            .await
            .map_err(|error| AppError::Sidecar(format!("write frame: {error}")))?;
        stream
            .write_all(&payload)
            .await
            .map_err(|error| AppError::Sidecar(format!("write payload: {error}")))?;
        stream
            .flush()
            .await
            .map_err(|error| AppError::Sidecar(format!("flush payload: {error}")))?;
        let size = stream
            .read_u32()
            .await
            .map_err(|error| AppError::Sidecar(format!("read frame: {error}")))?
            as usize;
        if size == 0 || size > MAX_FRAME_BYTES {
            return Err(AppError::Sidecar(
                "Sidecar returned an invalid frame length".to_owned(),
            ));
        }
        let mut response_payload = vec![0_u8; size];
        stream
            .read_exact(&mut response_payload)
            .await
            .map_err(|error| AppError::Sidecar(format!("read payload: {error}")))?;
        let response: JsonRpcResponse = serde_json::from_slice(&response_payload)
            .map_err(|error| AppError::Sidecar(format!("decode response: {error}")))?;
        if response.jsonrpc != "2.0" || response.id != request_id {
            return Err(AppError::Sidecar(
                "Sidecar response correlation failed".to_owned(),
            ));
        }
        if let Some(error) = response.error {
            let code = error
                .data
                .map(|data| data.code)
                .unwrap_or_else(|| format!("RPC_{}", error.code));
            return Err(AppError::Sidecar(format!("{code}: {}", error.message)));
        }
        let value = response
            .result
            .ok_or_else(|| AppError::Sidecar("RPC result is missing".to_owned()))?;
        serde_json::from_value(value).map_err(|error| {
            AppError::Sidecar(format!("RPC result does not match contract: {error}"))
        })
    }
}
