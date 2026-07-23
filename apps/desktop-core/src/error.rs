/// 应用错误类型，支持 Tauri IPC 序列化
use serde::Serialize;
use thiserror::Error;

#[derive(Error, Debug)]
pub enum AppError {
    #[error("Sidecar error: {0}")]
    Sidecar(String),

    #[error("Authentication error: {0}")]
    Auth(String),

    #[error("Validation error: {0}")]
    Validation(String),

    #[error("Not found: {0}")]
    NotFound(String),

    #[error("Network error: {0}")]
    Network(String),

    #[error("Storage error: {0}")]
    Storage(String),

    #[error("Security error: {0}")]
    Security(String),

    #[error("Internal error: {0}")]
    Internal(String),
}

#[derive(Serialize)]
struct AppErrorSerializable {
    error: String,
    code: String,
}

impl Serialize for AppError {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: serde::Serializer,
    {
        let (code, message) = match self {
            AppError::Sidecar(msg) => ("SIDECAR_ERROR", msg.clone()),
            AppError::Auth(msg) => ("AUTH_ERROR", msg.clone()),
            AppError::Validation(msg) => ("VALIDATION_ERROR", msg.clone()),
            AppError::NotFound(msg) => ("NOT_FOUND", msg.clone()),
            AppError::Network(msg) => ("NETWORK_ERROR", msg.clone()),
            AppError::Storage(msg) => ("STORAGE_ERROR", msg.clone()),
            AppError::Security(msg) => ("SECURITY_ERROR", msg.clone()),
            AppError::Internal(msg) => ("INTERNAL_ERROR", msg.clone()),
        };
        AppErrorSerializable {
            error: message,
            code: code.to_string(),
        }
        .serialize(serializer)
    }
}
