//! Authenticated, length-framed JSON-RPC client over a Unix domain socket.
//!
//! Uses a background reader task with a pending-map multiplexer so that
//! multiple concurrent `call()`s can have their responses matched by ID
//! rather than relying on serial request-response ordering.
//!
//! The reader task also handles reverse JSON-RPC requests from the sidecar,
//! dispatches them through the reverse handler table, and writes the response
//! frames back.  Direction is determined by the JSON-RPC shape (`method` for a
//! request, `result`/`error` for a response), never by an id naming convention.

use std::collections::HashMap;
use std::fmt;
use std::future::Future;
use std::path::{Path, PathBuf};
use std::pin::Pin;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::Duration;

use base64::{engine::general_purpose::STANDARD as BASE64, Engine as _};
use hmac::{Hmac, Mac};
use rand::RngCore;
use serde::de::DeserializeOwned;
use serde::Deserialize;
use serde_json::Value;
use sha2::Sha256;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::unix::{OwnedReadHalf, OwnedWriteHalf};
use tokio::net::UnixStream;
use tokio::sync::{oneshot, Mutex, Semaphore};
use tokio::task::JoinHandle;
use tokio::time::timeout;
use uuid::Uuid;
use zeroize::Zeroizing;

use crate::error::AppError;
use crate::ipc::dispatcher::ReverseMethodTable;
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

type PendingMap = HashMap<String, oneshot::Sender<Result<JsonRpcResponse, AppError>>>;
const MAX_REVERSE_INFLIGHT: usize = 256;
pub type DisconnectHook = Arc<dyn Fn() -> Pin<Box<dyn Future<Output = ()> + Send>> + Send + Sync>;

pub struct SidecarClient {
    socket_path: PathBuf,
    writer: Arc<Mutex<Option<OwnedWriteHalf>>>,
    ipc_session_id: Mutex<Option<Uuid>>,
    window_session_id: Uuid,
    pending: Arc<Mutex<PendingMap>>,
    reader_task: Mutex<Option<JoinHandle<()>>>,
    reverse_table: Arc<ReverseMethodTable>,
    disconnect_hook: Mutex<Option<DisconnectHook>>,
    disconnect_notified: Arc<AtomicBool>,
}

impl fmt::Debug for SidecarClient {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("SidecarClient")
            .field("socket_path", &self.socket_path)
            .field("window_session_id", &self.window_session_id)
            .finish_non_exhaustive()
    }
}

impl SidecarClient {
    pub fn new(socket_path: impl Into<PathBuf>, reverse_table: Arc<ReverseMethodTable>) -> Self {
        Self {
            socket_path: socket_path.into(),
            writer: Arc::new(Mutex::new(None)),
            ipc_session_id: Mutex::new(None),
            window_session_id: Uuid::new_v4(),
            pending: Arc::new(Mutex::new(HashMap::new())),
            reader_task: Mutex::new(None),
            reverse_table,
            disconnect_hook: Mutex::new(None),
            disconnect_notified: Arc::new(AtomicBool::new(false)),
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
        // A reconnect always starts from a clean authenticated stream.  The
        // old reader must be stopped and all pending calls must be failed
        // before a new writer is installed; otherwise responses from the
        // previous generation can be correlated with the new session.
        if self.ipc_session_id.lock().await.is_some()
            || self.reader_task.lock().await.is_some()
            || self.writer.lock().await.is_some()
        {
            self.disconnect().await;
        }
        if startup_token.len() != 32 {
            return Err(AppError::Security(
                "IPC startup token must contain 32 bytes".to_owned(),
            ));
        }
        let stream = UnixStream::connect(&self.socket_path)
            .await
            .map_err(|error| AppError::Sidecar(format!("connect UDS: {error}")))?;

        let (reader, writer_half) = stream.into_split();
        self.disconnect_notified.store(false, Ordering::SeqCst);
        {
            let mut w = self.writer.lock().await;
            *w = Some(writer_half);
        }
        let reader_writer = self.writer.clone();

        let pending = Arc::clone(&self.pending);
        let rev_table = Arc::clone(&self.reverse_table);
        let disconnect_hook = self.disconnect_hook.lock().await.clone();
        let disconnect_notified = Arc::clone(&self.disconnect_notified);
        let reverse_semaphore = Arc::new(Semaphore::new(MAX_REVERSE_INFLIGHT));
        let handle = tokio::spawn(async move {
            Self::reader_loop(
                reader,
                reader_writer,
                pending,
                rev_table,
                disconnect_hook,
                disconnect_notified,
                reverse_semaphore,
            )
            .await;
        });
        *self.reader_task.lock().await = Some(handle);

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
                window_session_id: Some(self.window_session_id),
                idempotency_key: None,
                deadline_at: None,
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
                window_session_id: Some(self.window_session_id),
                idempotency_key,
                deadline_at: Some(
                    (chrono::Utc::now() + chrono::Duration::seconds(30)).to_rfc3339(),
                ),
            },
        );
        self.exchange(request).await
    }

    /// Send a Rust→Sidecar notification on the already authenticated stream.
    /// Notifications deliberately have no id and therefore cannot consume a
    /// pending response slot or be mistaken for a reverse request.
    pub async fn notify(&self, method: &str, params: Value) -> Result<(), AppError> {
        let payload = serde_json::to_vec(&serde_json::json!({
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }))
        .map_err(|error| AppError::Internal(error.to_string()))?;
        if payload.is_empty() || payload.len() > MAX_FRAME_BYTES {
            return Err(AppError::Validation(
                "RPC notification exceeds frame limit".to_owned(),
            ));
        }
        let mut writer_guard = self.writer.lock().await;
        let writer = writer_guard
            .as_mut()
            .ok_or_else(|| AppError::Sidecar("Sidecar is disconnected".to_owned()))?;
        Self::write_frame(writer, &payload).await
    }

    pub async fn bind_disconnect_hook(&self, hook: DisconnectHook) {
        *self.disconnect_hook.lock().await = Some(hook);
    }

    pub async fn disconnect(&self) {
        self.notify_disconnect().await;
        // Cancel the background reader task.
        {
            let mut task = self.reader_task.lock().await;
            if let Some(handle) = task.take() {
                handle.abort();
            }
        }
        // Signal all pending callers with a disconnect error.
        {
            let mut pending = self.pending.lock().await;
            for (_, tx) in pending.drain() {
                let _ = tx.send(Err(AppError::Sidecar("Sidecar disconnected".to_owned())));
            }
        }
        *self.ipc_session_id.lock().await = None;
        *self.writer.lock().await = None;
    }

    async fn notify_disconnect(&self) {
        if self.disconnect_notified.swap(true, Ordering::SeqCst) {
            return;
        }
        let hook = self.disconnect_hook.lock().await.clone();
        if let Some(hook) = hook {
            hook().await;
        }
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
        let (tx, rx) = oneshot::channel();
        {
            let mut pending = self.pending.lock().await;
            if pending.len() >= 256 {
                return Err(AppError::Sidecar("IPC_PENDING_REQUEST_LIMIT".to_owned()));
            }
            pending.insert(request_id.clone(), tx);
        }
        {
            let mut writer_guard = self.writer.lock().await;
            let writer = writer_guard
                .as_mut()
                .ok_or_else(|| AppError::Sidecar("Sidecar is disconnected".to_owned()));
            let write_result = match writer {
                Ok(writer) => Self::write_frame(writer, &payload).await,
                Err(error) => Err(error),
            };
            if let Err(error) = write_result {
                self.pending.lock().await.remove(&request_id);
                return Err(error);
            }
        }
        let inner: Result<JsonRpcResponse, AppError> =
            match timeout(Duration::from_secs(30), rx).await {
                Ok(result) => result
                    .map_err(|_| AppError::Sidecar("Sidecar reader task terminated".to_owned()))?,
                Err(_) => {
                    self.pending.lock().await.remove(&request_id);
                    return Err(AppError::Sidecar("IPC_DEADLINE_EXCEEDED".to_owned()));
                }
            };
        let response: JsonRpcResponse = inner?;
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

    async fn write_frame(writer: &mut OwnedWriteHalf, payload: &[u8]) -> Result<(), AppError> {
        writer
            .write_all(&(payload.len() as u32).to_be_bytes())
            .await
            .map_err(|error| AppError::Sidecar(format!("write frame: {error}")))?;
        writer
            .write_all(payload)
            .await
            .map_err(|error| AppError::Sidecar(format!("write payload: {error}")))?;
        writer
            .flush()
            .await
            .map_err(|error| AppError::Sidecar(format!("flush payload: {error}")))?;
        Ok(())
    }

    async fn reader_loop(
        mut reader: OwnedReadHalf,
        writer: Arc<Mutex<Option<OwnedWriteHalf>>>,
        pending: Arc<Mutex<PendingMap>>,
        reverse_table: Arc<ReverseMethodTable>,
        disconnect_hook: Option<DisconnectHook>,
        disconnect_notified: Arc<AtomicBool>,
        reverse_semaphore: Arc<Semaphore>,
    ) {
        while let Ok(n) = reader.read_u32().await {
            let size = n as usize;
            if size == 0 || size > MAX_FRAME_BYTES {
                break;
            }
            let mut buf = vec![0_u8; size];
            if reader.read_exact(&mut buf).await.is_err() {
                break;
            }
            let value: Value = match serde_json::from_slice(&buf) {
                Ok(value) => value,
                Err(_) => break,
            };

            if let Some(method) = value
                .get("method")
                .and_then(Value::as_str)
                .map(str::to_owned)
            {
                // Reverse notifications intentionally omit both `id` and
                // `meta`.  They must be dispatched without trying to
                // deserialize into the normal request DTO (which requires
                // both fields), otherwise one heartbeat would tear down the
                // authenticated IPC reader and fail every pending call.
                let request_id = match value.get("id") {
                    None => None,
                    Some(Value::String(id)) => Some(id.clone()),
                    Some(_) => break,
                };
                let params = value.get("params").cloned().unwrap_or(Value::Null);
                let permit = match reverse_semaphore.clone().try_acquire_owned() {
                    Ok(permit) => permit,
                    Err(_) => {
                        if let Some(request_id) = request_id {
                            let payload = serde_json::to_vec(&serde_json::json!({
                                "jsonrpc": "2.0",
                                "id": request_id,
                                "error": {
                                    "code": -32000,
                                    "message": "IPC_BACKPRESSURE",
                                },
                            }));
                            if let Ok(payload) = payload {
                                let mut writer_guard = writer.lock().await;
                                if let Some(w) = writer_guard.as_mut() {
                                    if Self::write_frame(w, &payload).await.is_err() {
                                        break;
                                    }
                                }
                            }
                        }
                        continue;
                    }
                };
                let writer = writer.clone();
                let reverse_table = reverse_table.clone();
                tokio::spawn(async move {
                    let result = reverse_table.dispatch(&method, params).await;
                    let Some(request_id) = request_id else {
                        if let Err(error) = result {
                            tracing::debug!(%error, "reverse notification handler failed");
                        }
                        drop(permit);
                        return;
                    };
                    let response_payload = match result {
                        Ok(value) => serde_json::to_vec(&serde_json::json!({
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "result": value,
                        })),
                        Err(error) => serde_json::to_vec(&serde_json::json!({
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "error": {
                                "code": -32000,
                                "message": error.to_string(),
                            },
                        })),
                    };
                    if let Ok(payload) = response_payload {
                        let mut writer_guard = writer.lock().await;
                        if let Some(w) = writer_guard.as_mut() {
                            let _ = Self::write_frame(w, &payload).await;
                        }
                    }
                    drop(permit);
                });
                continue;
            }

            let response: JsonRpcResponse = match serde_json::from_value(value) {
                Ok(response) => response,
                Err(_) => break,
            };
            let mut pending = pending.lock().await;
            if let Some(tx) = pending.remove(&response.id) {
                let _ = tx.send(Ok(response));
            }
        }

        // A malformed frame or an EOF terminates the reader without going
        // through `disconnect()`.  Every caller waiting on the pending map
        // must be released immediately; otherwise the oneshot sender stays
        // owned by the map forever and the RPC future hangs until process
        // shutdown.  The writer is also cleared so subsequent calls fail
        // closed instead of writing to a half-closed stream.
        {
            let mut pending_guard = pending.lock().await;
            for (_, tx) in pending_guard.drain() {
                let _ = tx.send(Err(AppError::Sidecar("Sidecar connection lost".to_owned())));
            }
        }
        *writer.lock().await = None;
        // The owning SidecarClient may still be alive while the socket peer
        // disappears.  Notify the runtime supervisor exactly once so active
        // process groups and egress leases are revoked on an unexpected EOF.
        if !disconnect_notified.swap(true, Ordering::SeqCst) {
            if let Some(hook) = disconnect_hook {
                hook().await;
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn client_defaults() {
        let rev_table = Arc::new(ReverseMethodTable::new());
        let client = SidecarClient::new("/tmp/test.sock", rev_table);
        assert_eq!(client.socket_path(), Path::new("/tmp/test.sock"));
    }
}
