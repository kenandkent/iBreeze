/// RPC error types for IPC communication
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum RpcError {
    MethodNotFound { method: String },
    InvalidParams { detail: String },
    Internal { detail: String },
    Unauthorized { detail: String },
}

impl std::fmt::Display for RpcError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            RpcError::MethodNotFound { method } => write!(f, "Method not found: {method}"),
            RpcError::InvalidParams { detail } => write!(f, "Invalid params: {detail}"),
            RpcError::Internal { detail } => write!(f, "Internal error: {detail}"),
            RpcError::Unauthorized { detail } => write!(f, "Unauthorized: {detail}"),
        }
    }
}

impl std::error::Error for RpcError {}

impl RpcError {
    pub fn code(&self) -> i32 {
        match self {
            RpcError::MethodNotFound { .. } => -32601,
            RpcError::InvalidParams { .. } => -32602,
            RpcError::Internal { .. } => -32603,
            RpcError::Unauthorized { .. } => -32001,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_rpc_error_codes() {
        let err = RpcError::MethodNotFound { method: "test".to_string() };
        assert_eq!(err.code(), -32601);

        let err = RpcError::InvalidParams { detail: "bad".to_string() };
        assert_eq!(err.code(), -32602);

        let err = RpcError::Internal { detail: "oops".to_string() };
        assert_eq!(err.code(), -32603);

        let err = RpcError::Unauthorized { detail: "no".to_string() };
        assert_eq!(err.code(), -32001);
    }

    #[test]
    fn test_rpc_error_display() {
        let err = RpcError::MethodNotFound { method: "test".to_string() };
        assert!(err.to_string().contains("test"));
    }
}
