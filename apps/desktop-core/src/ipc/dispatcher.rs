use std::collections::HashMap;
use std::future::Future;
use std::pin::Pin;
use std::sync::Arc;

use chrono::{DateTime, Utc};
use serde_json::Value;

use super::multiplexer::IpcError;
use super::session::IpcSession;

pub type HandlerFn = Arc<dyn Fn(Value, IpcSession) -> Result<Value, IpcError> + Send + Sync>;

pub struct GeneratedDispatcher {
    handlers: HashMap<String, HandlerFn>,
}

impl GeneratedDispatcher {
    pub fn new() -> Self {
        Self {
            handlers: HashMap::new(),
        }
    }

    pub fn register(&mut self, method: &str, handler: HandlerFn) {
        self.handlers.insert(method.to_owned(), handler);
    }

    pub fn dispatch(
        &self,
        method: &str,
        params: Value,
        session: IpcSession,
    ) -> Result<Value, IpcError> {
        match self.handlers.get(method) {
            Some(handler) => handler(params, session),
            None => Err(IpcError::MethodNotAllowed),
        }
    }

    pub fn has_method(&self, method: &str) -> bool {
        self.handlers.contains_key(method)
    }

    pub fn method_count(&self) -> usize {
        self.handlers.len()
    }
}

impl Default for GeneratedDispatcher {
    fn default() -> Self {
        Self::new()
    }
}

pub struct ReverseMethodTable {
    methods: HashMap<String, ReverseHandler>,
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

pub async fn handle_frame(
    value: Value,
    dispatcher: &GeneratedDispatcher,
    reverse_table: &ReverseMethodTable,
    session: &IpcSession,
) -> Result<Option<Value>, IpcError> {
    let jsonrpc = value
        .get("jsonrpc")
        .and_then(|v| v.as_str())
        .unwrap_or("2.0");

    let method = match value.get("method").and_then(|v| v.as_str()) {
        Some(m) => m,
        None => return Err(IpcError::MethodNotAllowed),
    };

    let params = value.get("params").cloned().unwrap_or(Value::Null);
    let is_notification = value.get("id").is_none();
    let id = value
        .get("id")
        .and_then(|v| v.as_str())
        .map(|s| s.to_owned());

    let deadline_str = value
        .get("meta")
        .and_then(|m| m.get("deadline_at"))
        .and_then(|d| d.as_str());

    if let Some(deadline_str) = deadline_str {
        if let Ok(deadline) = DateTime::parse_from_rfc3339(deadline_str) {
            if deadline < Utc::now() {
                return if is_notification {
                    Ok(None)
                } else {
                    Err(IpcError::DeadlineExceeded)
                };
            }
        }
    }

    let is_reverse = id.as_deref().map_or(false, |id| id.starts_with("sidecar:"));

    let result = if is_reverse {
        reverse_table.dispatch(method, params).await
    } else {
        dispatcher.dispatch(method, params, session.clone())
    };

    if is_notification {
        if let Err(e) = &result {
            tracing::warn!(method, error = %e, "notification handler failed");
        }
        return Ok(None);
    }

    match result {
        Ok(response) => Ok(Some(serde_json::json!({
            "jsonrpc": jsonrpc,
            "id": id,
            "result": response,
        }))),
        Err(error) => Ok(Some(serde_json::json!({
            "jsonrpc": jsonrpc,
            "id": id,
            "error": {
                "code": -32000,
                "message": error.to_string(),
            },
        }))),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Arc;
    use tokio::sync::{mpsc, Mutex};
    use uuid::Uuid;

    use super::super::multiplexer::Multiplexer;
    use super::super::session::IpcSession;

    #[test]
    fn unknown_method_returns_method_not_allowed() {
        let dispatcher = GeneratedDispatcher::new();
        let reverse = ReverseMethodTable::new();
        let (tx, _rx) = mpsc::unbounded_channel();
        let mux = Arc::new(Mutex::new(Multiplexer::new(tx)));
        let (cancel_tx, _) = tokio::sync::watch::channel(false);
        let session = IpcSession::new(mux, cancel_tx);

        let value = serde_json::json!({
            "jsonrpc": "2.0",
            "id": "core:uuid",
            "method": "nonexistent.method",
            "params": {},
        });

        let result = tokio::runtime::Runtime::new()
            .unwrap()
            .block_on(handle_frame(value, &dispatcher, &reverse, &session));

        assert!(result.is_ok());
        let response = result.unwrap().unwrap();
        assert_eq!(response["error"]["message"], "METHOD_NOT_ALLOWED");
    }

    #[test]
    fn registered_method_is_dispatched() {
        let mut dispatcher = GeneratedDispatcher::new();
        dispatcher.register("test.echo", Arc::new(|params, _session| Ok(params)));
        let reverse = ReverseMethodTable::new();
        let (tx, _rx) = mpsc::unbounded_channel();
        let mux = Arc::new(Mutex::new(Multiplexer::new(tx)));
        let (cancel_tx, _) = tokio::sync::watch::channel(false);
        let session = IpcSession::new(mux, cancel_tx);

        let value = serde_json::json!({
            "jsonrpc": "2.0",
            "id": "core:uuid",
            "method": "test.echo",
            "params": {"hello": "world"},
        });

        let result = tokio::runtime::Runtime::new()
            .unwrap()
            .block_on(handle_frame(value, &dispatcher, &reverse, &session));

        assert!(result.is_ok());
        let response = result.unwrap().unwrap();
        assert_eq!(response["result"]["hello"], "world");
    }

    #[test]
    fn notification_returns_none() {
        let dispatcher = GeneratedDispatcher::new();
        let reverse = ReverseMethodTable::new();
        let (tx, _rx) = mpsc::unbounded_channel();
        let mux = Arc::new(Mutex::new(Multiplexer::new(tx)));
        let (cancel_tx, _) = tokio::sync::watch::channel(false);
        let session = IpcSession::new(mux, cancel_tx);

        let value = serde_json::json!({
            "jsonrpc": "2.0",
            "method": "some.notification",
            "params": {},
        });

        let result = tokio::runtime::Runtime::new()
            .unwrap()
            .block_on(handle_frame(value, &dispatcher, &reverse, &session));

        assert!(result.is_ok());
        assert!(result.unwrap().is_none());
    }

    #[test]
    fn reverse_method_routes_to_reverse_table() {
        let dispatcher = GeneratedDispatcher::new();
        let mut reverse = ReverseMethodTable::new();
        reverse.register(
            "runtime.process.status",
            Arc::new(|_params| {
                Box::pin(async move { Ok(serde_json::json!({"state": "running"})) })
            }),
        );

        let (tx, _rx) = mpsc::unbounded_channel();
        let mux = Arc::new(Mutex::new(Multiplexer::new(tx)));
        let (cancel_tx, _) = tokio::sync::watch::channel(false);
        let session = IpcSession::new(mux, cancel_tx);

        let value = serde_json::json!({
            "jsonrpc": "2.0",
            "id": "sidecar:uuid",
            "method": "runtime.process.status",
            "params": {},
        });

        let result = tokio::runtime::Runtime::new()
            .unwrap()
            .block_on(handle_frame(value, &dispatcher, &reverse, &session));

        assert!(result.is_ok());
        let response = result.unwrap().unwrap();
        assert_eq!(response["result"]["state"], "running");
    }

    #[test]
    fn expired_deadline_returns_deadline_exceeded() {
        let dispatcher = GeneratedDispatcher::new();
        let reverse = ReverseMethodTable::new();
        let (tx, _rx) = mpsc::unbounded_channel();
        let mux = Arc::new(Mutex::new(Multiplexer::new(tx)));
        let (cancel_tx, _) = tokio::sync::watch::channel(false);
        let session = IpcSession::new(mux, cancel_tx);

        let value = serde_json::json!({
            "jsonrpc": "2.0",
            "id": "core:uuid",
            "method": "test.method",
            "params": {},
            "meta": {
                "deadline_at": "2020-01-01T00:00:00Z",
            },
        });

        let result = tokio::runtime::Runtime::new()
            .unwrap()
            .block_on(handle_frame(value, &dispatcher, &reverse, &session));

        assert!(result.is_ok());
        let response = result.unwrap().unwrap();
        assert_eq!(response["error"]["message"], "IPC_DEADLINE_EXCEEDED");
    }
}
