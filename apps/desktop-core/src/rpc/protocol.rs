//! Strict local JSON-RPC 2.0 protocol shared with the Python Sidecar.

use serde::{Deserialize, Serialize};
use serde_json::Value;
use uuid::Uuid;

pub const JSON_RPC_VERSION: &str = "2.0";
pub const PROTOCOL_VERSION: u32 = 1;
pub const MAX_FRAME_BYTES: usize = 16 * 1024 * 1024;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct RpcMeta {
    pub trace_id: Uuid,
    pub ipc_session_id: Option<Uuid>,
    pub window_session_id: Uuid,
    pub idempotency_key: Option<Uuid>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct JsonRpcRequest {
    pub jsonrpc: String,
    pub id: String,
    pub method: String,
    pub params: Value,
    pub meta: RpcMeta,
}

impl JsonRpcRequest {
    pub fn new(method: impl Into<String>, params: Value, meta: RpcMeta) -> Self {
        Self {
            jsonrpc: JSON_RPC_VERSION.to_owned(),
            id: format!("core:{}", Uuid::new_v4()),
            method: method.into(),
            params,
            meta,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct JsonRpcResponse {
    pub jsonrpc: String,
    pub id: String,
    #[serde(default)]
    pub result: Option<Value>,
    #[serde(default)]
    pub error: Option<JsonRpcError>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct JsonRpcError {
    pub code: i32,
    pub message: String,
    #[serde(default)]
    pub data: Option<DomainErrorData>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DomainErrorData {
    pub code: String,
    pub trace_id: Uuid,
    #[serde(default)]
    pub field_errors: Vec<FieldError>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FieldError {
    pub path: String,
    pub message: String,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn request_has_core_uuid_and_exact_meta() {
        let request = JsonRpcRequest::new(
            "company.list",
            serde_json::json!({"filter": {}, "cursor": null, "limit": 50}),
            RpcMeta {
                trace_id: Uuid::new_v4(),
                ipc_session_id: Some(Uuid::new_v4()),
                window_session_id: Uuid::new_v4(),
                idempotency_key: None,
            },
        );
        assert!(request.id.starts_with("core:"));
        assert!(Uuid::parse_str(&request.id[5..]).is_ok());
        let value = serde_json::to_value(request).expect("serialize request");
        assert_eq!(value.as_object().expect("request object").len(), 5);
        assert_eq!(value["meta"].as_object().expect("meta object").len(), 4);
    }

    #[test]
    fn unknown_response_fields_are_rejected() {
        let response = serde_json::json!({
            "jsonrpc": "2.0",
            "id": format!("core:{}", Uuid::new_v4()),
            "result": {},
            "unexpected": true
        });
        assert!(serde_json::from_value::<JsonRpcResponse>(response).is_err());
    }
}
