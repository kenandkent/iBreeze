use std::path::PathBuf;

use serde::{Deserialize, Serialize};
use uuid::Uuid;

use crate::error::AppError;

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
    pub credential_ref: String,
    pub provider_id: Uuid,
    pub provider_version: u64,
    pub relative_path: String,
    pub headers: Vec<(String, String)>,
    pub body: Option<Vec<u8>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CredentialHttpCancel {
    pub request_id: Uuid,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CredentialProbe {
    pub credential_ref: String,
    pub provider_id: Uuid,
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
) -> Result<ExternalWriteResponse, AppError> {
    let target = PathBuf::from(&request.target_realpath);
    let canonical = target.canonicalize().map_err(|e| {
        AppError::Security(format!("host.externalWrite: target not accessible: {e}"))
    })?;
    let old_hash = compute_path_state_hash(&canonical)?;
    if old_hash != request.expected_old_sha256.as_deref().unwrap_or("") {
        return Err(AppError::Security("APPROVAL_TARGET_CHANGED".to_owned()));
    }
    Err(AppError::NotSupported(
        "host.externalWrite.execute stub: file system write not yet implemented".to_owned(),
    ))
}

pub async fn handle_process_registered(_event: ProcessEvent) -> Result<(), AppError> {
    Ok(())
}

pub async fn handle_process_exited(_event: ProcessEvent) -> Result<(), AppError> {
    Ok(())
}

fn compute_path_state_hash(_path: &std::path::Path) -> Result<String, AppError> {
    Ok(String::new())
}

pub async fn handle_credential_http_start(
    _request: CredentialHttpStart,
) -> Result<(), AppError> {
    Err(AppError::NotSupported(
        "credential.http.start: not yet implemented".to_owned(),
    ))
}

pub async fn handle_credential_http_cancel(
    _request: CredentialHttpCancel,
) -> Result<(), AppError> {
    Err(AppError::NotSupported(
        "credential.http.cancel: not yet implemented".to_owned(),
    ))
}

pub async fn handle_credential_probe(_request: CredentialProbe) -> Result<bool, AppError> {
    Err(AppError::NotSupported(
        "credential.probe: not yet implemented".to_owned(),
    ))
}

/// Allowed reverse methods from Sidecar to Rust
pub const ALLOWED_REVERSE_METHODS: &[&str] = &[
    "credential.http.start",
    "credential.http.cancel",
    "credential.probe",
    "host.externalWrite.execute",
];

/// Reverse notification methods (no id, no response)
pub const ALLOWED_REVERSE_NOTIFICATIONS: &[&str] =
    &["runtime.processRegistered", "runtime.processExited"];

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
        assert!(validate_reverse_method("runtime.processRegistered").is_ok());
        assert!(validate_reverse_method("runtime.processExited").is_ok());
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
