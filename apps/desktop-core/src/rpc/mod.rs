pub mod api_client;
pub mod error;
pub mod protocol;
pub mod sidecar;

pub use error::RpcError;

use protocol::{JsonRpcRequest, JsonRpcResponse};

pub type RpcHandler = fn(&JsonRpcRequest) -> Result<serde_json::Value, RpcError>;

pub struct RpcRouter {
    handlers: std::collections::HashMap<String, RpcHandler>,
}

impl RpcRouter {
    pub fn new() -> Self {
        Self {
            handlers: std::collections::HashMap::new(),
        }
    }

    pub fn register(&mut self, method: &str, handler: RpcHandler) {
        self.handlers.insert(method.to_string(), handler);
    }

    pub fn handle(&self, request: &JsonRpcRequest) -> JsonRpcResponse {
        match self.handlers.get(&request.method) {
            Some(handler) => match handler(request) {
                Ok(result) => JsonRpcResponse::success(result, request.id.clone()),
                Err(e) => JsonRpcResponse::error(e.code(), e.to_string(), request.id.clone()),
            },
            None => {
                let error = RpcError::MethodNotFound {
                    method: request.method.clone(),
                };
                JsonRpcResponse::error(error.code(), error.to_string(), request.id.clone())
            }
        }
    }
}

impl Default for RpcRouter {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn dummy_handler(_req: &JsonRpcRequest) -> Result<serde_json::Value, RpcError> {
        Ok(serde_json::json!({"status": "ok"}))
    }

    #[test]
    fn test_router_register_and_handle() {
        let mut router = RpcRouter::new();
        router.register("test.method", dummy_handler);

        let request = JsonRpcRequest {
            jsonrpc: "2.0".to_string(),
            method: "test.method".to_string(),
            params: None,
            id: Some(serde_json::json!(1)),
        };

        let response = router.handle(&request);
        assert!(response.result.is_some());
        assert!(response.error.is_none());
    }

    #[test]
    fn test_router_method_not_found() {
        let router = RpcRouter::new();
        let request = JsonRpcRequest {
            jsonrpc: "2.0".to_string(),
            method: "unknown.method".to_string(),
            params: None,
            id: Some(serde_json::json!(1)),
        };

        let response = router.handle(&request);
        assert!(response.error.is_some());
        assert_eq!(response.error.unwrap().code, -32601);
    }
}
