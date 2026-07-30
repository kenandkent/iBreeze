use std::collections::HashMap;
use std::sync::Arc;

use serde::{Deserialize, Serialize};
use serde_json::Value;
use tokio::sync::oneshot;
use uuid::Uuid;

use crate::broker::{CredentialStore, HttpBroker};
use crate::error::AppError;
use crate::ipc::dispatcher::ReverseMethodTable;
use crate::ipc::multiplexer::IpcError;
use crate::security::external_write::ReceiptStore;
use crate::security::grant_store::GrantStore;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct ExternalWriteRequest {
    pub approval_id: Uuid,
    pub run_id: Uuid,
    pub operation: ExternalWriteOperation,
    pub target_realpath: String,
    pub expected_old_sha256: Option<String>,
    pub source_relative_path: Option<String>,
    pub source_sha256: Option<String>,
    pub source_size: Option<u64>,
    pub expires_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum ExternalWriteOperation {
    #[serde(rename = "create_file")]
    CreateFile,
    #[serde(rename = "replace_file")]
    ReplaceFile,
    #[serde(rename = "delete_file")]
    DeleteFile,
    #[serde(rename = "create_directory")]
    CreateDirectory,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct ExternalWriteResponse {
    pub approval_id: Uuid,
    pub run_id: Uuid,
    pub operation: ExternalWriteOperation,
    pub target_realpath: String,
    pub result_state_sha256: String,
    pub completed_at: String,
    pub receipt_sha256: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CredentialHttpStart {
    pub run_id: Uuid,
    pub credential_ref: Uuid,
    pub provider_release_id: Uuid,
    pub model_binding_id: Uuid,
    pub protocol: String,
    pub operation: String,
    pub relative_path: String,
    pub request: Value,
    pub deadline_at: String,
    pub provider_base_url: String,
    pub profile_directory_id: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CredentialHttpCancel {
    pub run_id: Uuid,
    pub request_id: Uuid,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CredentialProbe {
    pub credential_ref: Uuid,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ProcessEvent {
    pub pid: u32,
    pub pgid: u32,
    pub start_time: String,
    pub executable: String,
    pub parent_pid: u32,
}

pub async fn handle_external_write_execute(
    request: ExternalWriteRequest,
    grant_store: &GrantStore,
    receipt_store: &ReceiptStore,
) -> Result<ExternalWriteResponse, AppError> {
    crate::security::external_write::handle_external_write_execute(
        request,
        grant_store,
        receipt_store,
    )
    .await
}

pub async fn handle_process_registered(_event: ProcessEvent) -> Result<(), AppError> {
    Ok(())
}

pub async fn handle_process_exited(_event: ProcessEvent) -> Result<(), AppError> {
    Ok(())
}

pub struct ReverseBroker {
    pub http_broker: Arc<HttpBroker>,
    pub credential_store: Arc<CredentialStore>,
    cancel_senders: tokio::sync::RwLock<HashMap<Uuid, oneshot::Sender<()>>>,
}

impl ReverseBroker {
    pub fn new(http_broker: Arc<HttpBroker>, credential_store: Arc<CredentialStore>) -> Self {
        Self {
            http_broker,
            credential_store,
            cancel_senders: tokio::sync::RwLock::new(HashMap::new()),
        }
    }

    pub async fn handle_credential_http_start(
        &self,
        request: CredentialHttpStart,
    ) -> Result<Value, AppError> {
        let deadline_s = parse_deadline(&request.deadline_at).unwrap_or(300);
        let (request_id, cancel_tx) = self
            .http_broker
            .start(
                &request.profile_directory_id,
                &request.provider_base_url,
                request.credential_ref,
                request.provider_release_id,
                request.model_binding_id,
                request.run_id,
                &request.relative_path,
                request.request,
                deadline_s,
            )
            .await?;
        self.cancel_senders
            .write()
            .await
            .insert(request_id, cancel_tx);
        Ok(serde_json::json!({
            "request_id": request_id,
            "status": "accepted",
        }))
    }

    pub async fn handle_credential_http_cancel(
        &self,
        request: CredentialHttpCancel,
    ) -> Result<Value, AppError> {
        let mut senders = self.cancel_senders.write().await;
        if let Some(cancel_tx) = senders.remove(&request.request_id) {
            let _ = cancel_tx.send(());
            Ok(serde_json::json!({"status": "cancelled"}))
        } else {
            Err(AppError::NotFound(
                "Request not found or already completed".to_owned(),
            ))
        }
    }

    pub async fn handle_credential_probe(
        &self,
        request: CredentialProbe,
        profile_directory_id: &str,
    ) -> Result<Value, AppError> {
        self.credential_store
            .load_keychain_credential(profile_directory_id, request.credential_ref)?;
        Ok(serde_json::json!({"status": "ok"}))
    }
}

fn parse_deadline(rfc3339: &str) -> Option<u64> {
    chrono::DateTime::parse_from_rfc3339(rfc3339)
        .ok()
        .map(|dt| {
            let now = chrono::Utc::now();
            let dur = dt.signed_duration_since(now);
            dur.num_seconds().max(1) as u64
        })
}

/// Register all reverse handlers into a ReverseMethodTable.
pub fn register_reverse_handlers(
    table: &mut ReverseMethodTable,
    http_broker: Arc<HttpBroker>,
    credential_store: Arc<CredentialStore>,
) {
    let broker = Arc::new(ReverseBroker::new(http_broker, credential_store));
    let broker_clone = broker.clone();
    table.register(
        "credential.http.start",
        Arc::new(move |params| {
            let broker = broker_clone.clone();
            Box::pin(async move {
                let request: CredentialHttpStart = serde_json::from_value(params)
                    .map_err(|e| IpcError::Internal(e.to_string()))?;
                let result = broker.handle_credential_http_start(request).await;
                result.map_err(|e| IpcError::Internal(e.to_string()))
            })
        }),
    );
    let broker_clone = broker.clone();
    table.register(
        "credential.http.cancel",
        Arc::new(move |params| {
            let broker = broker_clone.clone();
            Box::pin(async move {
                let request: CredentialHttpCancel = serde_json::from_value(params)
                    .map_err(|e| IpcError::Internal(e.to_string()))?;
                let result = broker.handle_credential_http_cancel(request).await;
                result.map_err(|e| IpcError::Internal(e.to_string()))
            })
        }),
    );
    let broker_clone = broker.clone();
    table.register(
        "credential.probe",
        Arc::new(move |params| {
            let broker = broker_clone.clone();
            Box::pin(async move {
                let request: CredentialProbe = serde_json::from_value(params.clone())
                    .map_err(|e| IpcError::Internal(e.to_string()))?;
                let profile_id = params
                    .get("profile_directory_id")
                    .and_then(|v| v.as_str())
                    .unwrap_or("default");
                let result = broker.handle_credential_probe(request, profile_id).await;
                result.map_err(|e| IpcError::Internal(e.to_string()))
            })
        }),
    );
    table.register(
        "runtime.processRegistered",
        Arc::new(|params| {
            Box::pin(async move {
                let _event: ProcessEvent = serde_json::from_value(params)
                    .map_err(|e| IpcError::Internal(e.to_string()))?;
                handle_process_registered(_event)
                    .await
                    .map_err(|e| IpcError::Internal(e.to_string()))?;
                Ok(serde_json::json!({"status": "accepted"}))
            })
        }),
    );
    table.register(
        "runtime.processExited",
        Arc::new(|params| {
            Box::pin(async move {
                let _event: ProcessEvent = serde_json::from_value(params)
                    .map_err(|e| IpcError::Internal(e.to_string()))?;
                handle_process_exited(_event)
                    .await
                    .map_err(|e| IpcError::Internal(e.to_string()))?;
                Ok(serde_json::json!({"status": "accepted"}))
            })
        }),
    );
}

/// Allowed reverse methods from Sidecar to Rust
pub const ALLOWED_REVERSE_METHODS: &[&str] = &[
    "credential.http.start",
    "credential.http.cancel",
    "credential.probe",
    "host.externalWrite.execute",
    "runtime.process.start",
    "runtime.process.cancel",
    "runtime.process.status",
];

/// Reverse notification methods (no id, no response)
pub const ALLOWED_REVERSE_NOTIFICATIONS: &[&str] = &[
    "credential.http.event",
    "runtime.process.registered",
    "runtime.process.output",
    "runtime.process.exited",
];

pub fn validate_reverse_method(method: &str) -> Result<(), AppError> {
    if ALLOWED_REVERSE_METHODS.contains(&method) || ALLOWED_REVERSE_NOTIFICATIONS.contains(&method)
    {
        Ok(())
    } else {
        Err(AppError::Validation(format!(
            "METHOD_NOT_ALLOWED: {method}"
        )))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn allowed_reverse_methods_are_complete() {
        assert!(validate_reverse_method("credential.http.start").is_ok());
        assert!(validate_reverse_method("credential.http.cancel").is_ok());
        assert!(validate_reverse_method("credential.probe").is_ok());
        assert!(validate_reverse_method("host.externalWrite.execute").is_ok());
        assert!(validate_reverse_method("runtime.process.start").is_ok());
        assert!(validate_reverse_method("runtime.process.cancel").is_ok());
        assert!(validate_reverse_method("runtime.process.status").is_ok());
        assert!(validate_reverse_method("runtime.process.registered").is_ok());
        assert!(validate_reverse_method("runtime.process.output").is_ok());
        assert!(validate_reverse_method("runtime.process.exited").is_ok());
    }

    #[test]
    fn unknown_reverse_method_is_rejected() {
        assert!(validate_reverse_method("system.shutdown").is_err());
        assert!(validate_reverse_method("auth.login").is_err());
    }

    #[test]
    fn external_write_request_serialization_roundtrip() {
        let req = ExternalWriteRequest {
            approval_id: Uuid::new_v4(),
            run_id: Uuid::new_v4(),
            operation: ExternalWriteOperation::CreateFile,
            target_realpath: "/tmp/test.txt".to_owned(),
            expected_old_sha256: None,
            source_relative_path: Some("test.txt".to_owned()),
            source_sha256: Some("abc".to_owned()),
            source_size: Some(3),
            expires_at: "2026-12-31T23:59:59Z".to_owned(),
        };
        let json = serde_json::to_string(&req).expect("serialize");
        let deserialized: ExternalWriteRequest = serde_json::from_str(&json).expect("deserialize");
        assert_eq!(req.approval_id, deserialized.approval_id);
        assert_eq!(req.operation, deserialized.operation);
    }
}
