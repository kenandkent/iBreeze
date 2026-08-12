use std::collections::HashMap;
use std::future::Future;
use std::pin::Pin;
use std::sync::Arc;

use serde_json::Value;

use super::error::IpcError;

/// Reverse calls are dispatched by the single reader task owned by
/// `rpc::sidecar::SidecarClient`.  Keeping only this table here prevents the
/// old second reader/multiplexer stack from being accidentally used in
/// production.
pub struct ReverseMethodTable {
    methods: HashMap<String, ReverseHandler>,
}

impl std::fmt::Debug for ReverseMethodTable {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter
            .debug_struct("ReverseMethodTable")
            .field("method_count", &self.methods.len())
            .finish()
    }
}

type ReverseHandler = Arc<
    dyn Fn(Value) -> Pin<Box<dyn Future<Output = Result<Value, IpcError>> + Send>> + Send + Sync,
>;

impl ReverseMethodTable {
    pub fn new() -> Self {
        Self {
            methods: HashMap::new(),
        }
    }

    pub fn register(&mut self, method: &str, handler: ReverseHandler) {
        self.methods.insert(method.to_owned(), handler);
    }

    pub async fn dispatch(&self, method: &str, params: Value) -> Result<Value, IpcError> {
        match self.methods.get(method) {
            Some(handler) => handler(params).await,
            None => Err(IpcError::MethodNotAllowed),
        }
    }

    pub fn has_method(&self, method: &str) -> bool {
        self.methods.contains_key(method)
    }
}

impl Default for ReverseMethodTable {
    fn default() -> Self {
        Self::new()
    }
}
