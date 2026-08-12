use std::collections::HashMap;
use std::sync::Arc;

use serde::{Deserialize, Serialize};
use serde_json::Value;
use tokio::sync::{oneshot, RwLock};
use uuid::Uuid;

use crate::broker::{CredentialStore, HttpBroker};
use crate::error::AppError;
use crate::ipc::dispatcher::ReverseMethodTable;
use crate::ipc::error::IpcError;
use crate::process::{
    CancelProcessRequest, ProcessRequest, ProcessSupervisor, StartProcessRequest,
};
use crate::rpc::sidecar::SidecarClient;
use crate::security::external_write::ReceiptStore;
use crate::security::grant_store::GrantStore;

type CancelSender = (Uuid, oneshot::Sender<()>);
type CancelSenderMap = Arc<RwLock<HashMap<Uuid, CancelSender>>>;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ProviderProtocol {
    OpenaiResponses,
    AnthropicMessages,
    OpenaiChatCompletions,
}

impl ProviderProtocol {
    fn as_str(&self) -> &'static str {
        match self {
            Self::OpenaiResponses => "openai_responses",
            Self::AnthropicMessages => "anthropic_messages",
            Self::OpenaiChatCompletions => "openai_chat_completions",
        }
    }

    fn expected_path(&self) -> &'static str {
        match self {
            Self::OpenaiResponses => "/v1/responses",
            Self::AnthropicMessages => "/v1/messages",
            Self::OpenaiChatCompletions => "/v1/chat/completions",
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ProviderOperation {
    ModelTurn,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CatalogModelBinding {
    pub binding_id: Uuid,
    pub model_id: Uuid,
    pub provider_model_name: String,
    pub request_defaults: Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CatalogAgentBinding {
    pub agent_release_id: Uuid,
    pub key: String,
    #[serde(default)]
    pub network_domains: Vec<String>,
    #[serde(default)]
    pub version_ranges: Vec<CatalogAgentVersionRange>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CatalogAgentVersionRange {
    pub min_version: String,
    pub max_version_exclusive: String,
    pub executable_names: Vec<String>,
    pub supported_platforms: Vec<String>,
    pub probe_argv: Vec<String>,
    pub adapter_contract_version: u32,
    #[serde(default)]
    pub capability_tags: Vec<String>,
    #[serde(default)]
    pub network_domains: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CatalogProviderBinding {
    pub provider_release_id: Uuid,
    pub key: String,
    pub protocol: ProviderProtocol,
    pub base_url: String,
    pub auth_scheme: String,
    pub model_bindings: Vec<CatalogModelBinding>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CatalogSnapshot {
    pub release_id: Uuid,
    pub release_sequence: u64,
    #[serde(default)]
    pub agents: Vec<CatalogAgentBinding>,
    pub providers: Vec<CatalogProviderBinding>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct ExternalWriteRequest {
    pub approval_id: Uuid,
    pub workspace_grant_id: Uuid,
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
    pub protocol: ProviderProtocol,
    pub operation: ProviderOperation,
    pub relative_path: String,
    pub request: Value,
    pub deadline_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CredentialHttpCancel {
    pub run_id: Uuid,
    pub request_id: Uuid,
    #[serde(default)]
    pub reason: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CredentialProbe {
    pub credential_ref: Uuid,
    pub provider_release_id: Uuid,
    pub model_binding_id: Uuid,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CredentialProbeState {
    Ready,
    CredentialMissing,
    CredentialCorrupt,
    ProviderUnreachable,
    ProviderRejected,
    ConfigurationInvalid,
}

#[derive(Debug, Clone, Serialize)]
pub struct CredentialProbeResponse {
    pub available: bool,
    pub state: CredentialProbeState,
    pub checked_at: String,
    pub error_code: Option<String>,
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

#[derive(Clone)]
pub struct ReverseBroker {
    pub http_broker: Arc<HttpBroker>,
    pub credential_store: Arc<CredentialStore>,
    cancel_senders: CancelSenderMap,
    terminal_requests: Arc<RwLock<HashMap<Uuid, Value>>>,
    notification_client: Arc<RwLock<Option<std::sync::Weak<SidecarClient>>>>,
    profile_directory_id: Arc<RwLock<Option<String>>>,
    catalog: Arc<RwLock<Option<CatalogSnapshot>>>,
}

impl ReverseBroker {
    pub fn new(http_broker: Arc<HttpBroker>, credential_store: Arc<CredentialStore>) -> Self {
        Self {
            http_broker,
            credential_store,
            cancel_senders: Arc::new(RwLock::new(HashMap::new())),
            terminal_requests: Arc::new(RwLock::new(HashMap::new())),
            notification_client: Arc::new(RwLock::new(None)),
            profile_directory_id: Arc::new(RwLock::new(None)),
            catalog: Arc::new(RwLock::new(None)),
        }
    }

    pub async fn bind_client(&self, client: Option<Arc<SidecarClient>>) {
        *self.notification_client.write().await = client.map(|value| Arc::downgrade(&value));
    }

    pub async fn bind_profile(&self, profile_directory_id: Option<String>) {
        *self.profile_directory_id.write().await = profile_directory_id;
    }

    pub async fn bind_catalog(&self, snapshot: Option<CatalogSnapshot>) {
        *self.catalog.write().await = snapshot;
    }

    /// Cancel every provider request owned by the current authenticated IPC
    /// generation.  Reverse RPC tasks may outlive the reader that started
    /// them; draining the sender map here makes a UDS disconnect revoke both
    /// the credential lease and the per-request egress lease instead of
    /// leaving an API Model request running until its provider timeout.
    pub async fn cancel_all(&self) -> usize {
        let senders = {
            let mut guard = self.cancel_senders.write().await;
            guard
                .drain()
                .map(|(_, (_, sender))| sender)
                .collect::<Vec<_>>()
        };
        let count = senders.len();
        for sender in senders {
            let _ = sender.send(());
        }
        self.terminal_requests.write().await.clear();
        count
    }

    async fn notify(&self, method: &str, params: Value) -> Result<(), AppError> {
        let client = self
            .notification_client
            .read()
            .await
            .as_ref()
            .and_then(std::sync::Weak::upgrade);
        let Some(client) = client else { return Ok(()) };
        tokio::time::timeout(
            std::time::Duration::from_secs(5),
            client.notify(method, params),
        )
        .await
        .map_err(|_| AppError::Sidecar("IPC_BACKPRESSURE".to_owned()))??;
        Ok(())
    }

    pub async fn handle_credential_http_start(
        &self,
        request: CredentialHttpStart,
    ) -> Result<Value, AppError> {
        let deadline_s = parse_deadline(&request.deadline_at)
            .ok_or_else(|| AppError::Validation("PROVIDER_DEADLINE_INVALID".to_owned()))?;
        let profile_directory_id = self
            .profile_directory_id
            .read()
            .await
            .clone()
            .ok_or_else(|| AppError::Auth("PROFILE_NOT_OPEN".to_owned()))?;
        let provider = self
            .resolve_provider(
                request.provider_release_id,
                request.model_binding_id,
                &request.protocol,
                &request.relative_path,
            )
            .await?;
        let credential = self
            .credential_store
            .load_keychain_credential(&profile_directory_id, request.credential_ref)?;
        if credential.provider_id != request.provider_release_id {
            return Err(AppError::Validation(
                "CREDENTIAL_PROVIDER_MISMATCH".to_owned(),
            ));
        }
        let request_body = prepare_provider_request(&request.request, &provider)?;
        let (request_id, cancel_tx, mut receiver) = self
            .http_broker
            .start(
                &profile_directory_id,
                &provider.base_url,
                &provider.auth_scheme,
                request.credential_ref,
                request.provider_release_id,
                request.model_binding_id,
                request.run_id,
                &request.relative_path,
                request_body,
                deadline_s,
            )
            .await?;
        self.cancel_senders
            .write()
            .await
            .insert(request_id, (request.run_id, cancel_tx));
        let broker = self.clone();
        let run_id = request.run_id;
        tokio::spawn(async move {
            let timeout = tokio::time::sleep(std::time::Duration::from_secs(deadline_s.max(1)));
            tokio::pin!(timeout);
            loop {
                tokio::select! {
                    _ = &mut timeout => {
                        if let Some((_run_id, cancel_tx)) = broker.cancel_senders.write().await.remove(&request_id) {
                            let _ = cancel_tx.send(());
                        }
                        broker.terminal_requests.write().await.insert(request_id, serde_json::json!({
                            "request_id": request_id,
                            "run_id": run_id,
                            "state": "failed",
                            "last_sequence": 0,
                            "ended_at": chrono::Utc::now().to_rfc3339(),
                            "error_code": "PROVIDER_DEADLINE_EXCEEDED",
                        }));
                        break;
                    }
                    event = receiver.recv() => {
                        let Some(event) = event else {
                            broker.cancel_senders.write().await.remove(&request_id);
                            broker.terminal_requests.write().await.insert(request_id, serde_json::json!({
                                "request_id": request_id,
                                "run_id": run_id,
                                "state": "failed",
                                "last_sequence": 0,
                                "ended_at": chrono::Utc::now().to_rfc3339(),
                                "error_code": "PROVIDER_STREAM_CLOSED",
                            }));
                            break;
                        };
                        let is_terminal = matches!(
                            event.event,
                            crate::broker::http_stream::BrokerEventKind::Completed
                                | crate::broker::http_stream::BrokerEventKind::Failed
                        );
                        let _ = broker.notify("credential.http.event", serde_json::json!({
                            "request_id": request_id,
                            "run_id": run_id,
                            "sequence": event.sequence,
                            "event": event.event,
                            "payload": event.payload,
                            "received_at": event.received_at.to_rfc3339(),
                        })).await;
                        if is_terminal {
                            let state = if event.event == crate::broker::http_stream::BrokerEventKind::Failed {
                                "failed"
                            } else if event.payload.get("state").and_then(Value::as_str) == Some("cancelled") {
                                "cancelled"
                            } else {
                                "completed"
                            };
                            broker.terminal_requests.write().await.insert(request_id, serde_json::json!({
                                "request_id": request_id,
                                "run_id": run_id,
                                "state": state,
                                "last_sequence": event.sequence,
                                "ended_at": chrono::Utc::now().to_rfc3339(),
                            }));
                            broker.cancel_senders.write().await.remove(&request_id);
                            break;
                        }
                    }
                }
            }
        });
        Ok(serde_json::json!({
            "request_id": request_id,
            "accepted": true,
            "stream": true,
        }))
    }

    pub async fn handle_credential_http_cancel(
        &self,
        request: CredentialHttpCancel,
    ) -> Result<Value, AppError> {
        if request.reason.is_empty() || request.reason.len() > 500 {
            return Err(AppError::Validation("CANCEL_REASON_INVALID".to_owned()));
        }
        let mut senders = self.cancel_senders.write().await;
        if let Some((run_id, _)) = senders.get(&request.request_id) {
            if *run_id != request.run_id {
                return Err(AppError::Unauthorized("REQUEST_RUN_MISMATCH".to_owned()));
            }
        }
        if let Some((_run_id, cancel_tx)) = senders.remove(&request.request_id) {
            let _ = cancel_tx.send(());
            drop(senders);
            for _ in 0..300 {
                if let Some(response) = self
                    .terminal_requests
                    .read()
                    .await
                    .get(&request.request_id)
                    .cloned()
                {
                    return Ok(response);
                }
                tokio::time::sleep(std::time::Duration::from_millis(100)).await;
            }
            return Err(AppError::Network(
                "CREDENTIAL_HTTP_CANCEL_TIMEOUT".to_owned(),
            ));
        }
        drop(senders);
        if let Some(value) = self
            .terminal_requests
            .read()
            .await
            .get(&request.request_id)
            .cloned()
        {
            let expected_run_id = request.run_id.to_string();
            if value.get("run_id").and_then(Value::as_str) == Some(expected_run_id.as_str()) {
                return Ok(value);
            }
            return Err(AppError::Unauthorized("REQUEST_RUN_MISMATCH".to_owned()));
        }
        Err(AppError::NotFound(
            "Request not found or already completed".to_owned(),
        ))
    }

    pub async fn handle_credential_probe(
        &self,
        request: CredentialProbe,
    ) -> Result<Value, AppError> {
        let profile_directory_id = self
            .profile_directory_id
            .read()
            .await
            .clone()
            .ok_or_else(|| AppError::Auth("PROFILE_NOT_OPEN".to_owned()))?;
        let catalog = self.catalog.read().await.clone();
        let Some(snapshot) = catalog else {
            return Ok(serialize_probe_error(AppError::Validation(
                "CATALOG_NOT_AVAILABLE".to_owned(),
            )));
        };
        let provider = match resolve_provider(
            &snapshot,
            request.provider_release_id,
            request.model_binding_id,
        ) {
            Ok(value) => value,
            Err(error) => return Ok(serialize_probe_error(error)),
        };
        let credential = match self
            .credential_store
            .load_keychain_credential(&profile_directory_id, request.credential_ref)
        {
            Ok(value) => value,
            Err(error) => {
                let state = match error {
                    AppError::NotFound(_) => CredentialProbeState::CredentialMissing,
                    AppError::Security(_) => CredentialProbeState::CredentialCorrupt,
                    _ => CredentialProbeState::ConfigurationInvalid,
                };
                return serde_json::to_value(CredentialProbeResponse {
                    available: false,
                    state,
                    checked_at: chrono::Utc::now().to_rfc3339(),
                    error_code: Some("CREDENTIAL_NOT_READY".to_owned()),
                })
                .map_err(|error| AppError::Internal(error.to_string()));
            }
        };
        if credential.provider_id != request.provider_release_id {
            return Ok(serialize_probe_error(AppError::Validation(
                "CREDENTIAL_PROVIDER_MISMATCH".to_owned(),
            )));
        }

        let (relative_path, request_body) = probe_request(&provider.protocol);
        let run_id = Uuid::new_v4();
        let result = self
            .http_broker
            .start(
                &profile_directory_id,
                &provider.base_url,
                &provider.auth_scheme,
                request.credential_ref,
                request.provider_release_id,
                request.model_binding_id,
                run_id,
                relative_path,
                request_body,
                15,
            )
            .await;
        let (request_id, cancel_tx, receiver) = match result {
            Ok(value) => value,
            Err(error) => return Ok(serialize_probe_error(error)),
        };
        match self
            .http_broker
            .wait_for_receiver(request_id, receiver, 15)
            .await
        {
            Ok(_) => serde_json::to_value(CredentialProbeResponse {
                available: true,
                state: CredentialProbeState::Ready,
                checked_at: chrono::Utc::now().to_rfc3339(),
                error_code: None,
            })
            .map_err(|error| AppError::Internal(error.to_string())),
            Err(error) => {
                let _ = cancel_tx.send(());
                Ok(serialize_probe_error(error))
            }
        }
    }

    async fn resolve_provider(
        &self,
        provider_release_id: Uuid,
        model_binding_id: Uuid,
        protocol: &ProviderProtocol,
        relative_path: &str,
    ) -> Result<ResolvedProvider, AppError> {
        let catalog = self.catalog.read().await;
        let snapshot = catalog
            .as_ref()
            .ok_or_else(|| AppError::Validation("CATALOG_NOT_AVAILABLE".to_owned()))?;
        let provider = resolve_provider(snapshot, provider_release_id, model_binding_id)?;
        if provider.protocol.as_str() != protocol.as_str()
            || protocol.expected_path() != relative_path
        {
            return Err(AppError::Validation(
                "PROVIDER_OPERATION_NOT_ALLOWED".to_owned(),
            ));
        }
        Ok(provider)
    }
}

fn probe_request(protocol: &ProviderProtocol) -> (&'static str, Value) {
    match protocol {
        ProviderProtocol::OpenaiResponses => (
            "/v1/responses",
            serde_json::json!({"input": "ping", "max_output_tokens": 1, "store": false}),
        ),
        ProviderProtocol::AnthropicMessages => (
            "/v1/messages",
            serde_json::json!({"messages": [{"role": "user", "content": "ping"}], "max_tokens": 1}),
        ),
        ProviderProtocol::OpenaiChatCompletions => (
            "/v1/chat/completions",
            serde_json::json!({"messages": [{"role": "user", "content": "ping"}], "max_tokens": 1}),
        ),
    }
}

fn serialize_probe_error(error: AppError) -> Value {
    let (state, error_code) = match error {
        AppError::NotFound(_) => (
            CredentialProbeState::CredentialMissing,
            "CREDENTIAL_MISSING",
        ),
        AppError::Security(_) => (
            CredentialProbeState::CredentialCorrupt,
            "CREDENTIAL_CORRUPT",
        ),
        AppError::Unauthorized(_) => (CredentialProbeState::ProviderRejected, "PROVIDER_REJECTED"),
        AppError::Network(_) => (
            CredentialProbeState::ProviderUnreachable,
            "PROVIDER_UNREACHABLE",
        ),
        AppError::Validation(_) => (
            CredentialProbeState::ConfigurationInvalid,
            "CONFIGURATION_INVALID",
        ),
        _ => (
            CredentialProbeState::ProviderUnreachable,
            "PROVIDER_UNREACHABLE",
        ),
    };
    serde_json::to_value(CredentialProbeResponse {
        available: false,
        state,
        checked_at: chrono::Utc::now().to_rfc3339(),
        error_code: Some(error_code.to_owned()),
    })
    .unwrap_or_else(|_| {
        serde_json::json!({
            "available": false,
            "state": "provider_unreachable",
            "checked_at": chrono::Utc::now().to_rfc3339(),
            "error_code": "PROVIDER_UNREACHABLE"
        })
    })
}

#[derive(Debug, Clone)]
struct ResolvedProvider {
    base_url: String,
    auth_scheme: String,
    model_name: String,
    request_defaults: Value,
    protocol: ProviderProtocol,
}

fn resolve_provider(
    snapshot: &CatalogSnapshot,
    provider_release_id: Uuid,
    model_binding_id: Uuid,
) -> Result<ResolvedProvider, AppError> {
    let provider = snapshot
        .providers
        .iter()
        .find(|value| value.provider_release_id == provider_release_id)
        .ok_or_else(|| AppError::Validation("CATALOG_PROVIDER_NOT_FOUND".to_owned()))?;
    let binding = provider
        .model_bindings
        .iter()
        .find(|value| value.binding_id == model_binding_id)
        .ok_or_else(|| AppError::Validation("CATALOG_MODEL_BINDING_NOT_FOUND".to_owned()))?;
    Ok(ResolvedProvider {
        base_url: provider.base_url.clone(),
        auth_scheme: provider.auth_scheme.clone(),
        model_name: binding.provider_model_name.clone(),
        request_defaults: binding.request_defaults.clone(),
        protocol: provider.protocol.clone(),
    })
}

fn prepare_provider_request(
    request: &Value,
    provider: &ResolvedProvider,
) -> Result<Value, AppError> {
    let Value::Object(mut request) = request.clone() else {
        return Err(AppError::Validation(
            "PROVIDER_REQUEST_OBJECT_REQUIRED".to_owned(),
        ));
    };
    for forbidden in [
        "url",
        "base_url",
        "authorization",
        "api_key",
        "token",
        "proxy",
        // These fields are owned by the signed catalog/runtime contract.  A
        // Sidecar request may provide messages and model-specific input, but
        // it cannot turn off streaming or replace the tool schema that the
        // built-in Agent Loop supplied.
        "stream",
        "tool_choice",
        "functions",
        "function_call",
        "timeout",
        "timeout_seconds",
    ] {
        if request.contains_key(forbidden) {
            return Err(AppError::Validation(
                "PROVIDER_REQUEST_FIELD_FORBIDDEN".to_owned(),
            ));
        }
    }
    if request.contains_key("model") {
        return Err(AppError::Validation(
            "PROVIDER_MODEL_OVERRIDE_FORBIDDEN".to_owned(),
        ));
    }
    if let Some(tools) = request.get("tools") {
        validate_tool_schema(tools)?;
    }
    if let Value::Object(defaults) = &provider.request_defaults {
        for (key, value) in defaults {
            request.entry(key.clone()).or_insert_with(|| value.clone());
        }
    }
    request.insert(
        "model".to_owned(),
        Value::String(provider.model_name.clone()),
    );
    request.insert("stream".to_owned(), Value::Bool(true));
    Ok(Value::Object(request))
}

fn validate_tool_schema(value: &Value) -> Result<(), AppError> {
    let Value::Array(tools) = value else {
        return Err(AppError::Validation(
            "PROVIDER_TOOL_SCHEMA_INVALID".to_owned(),
        ));
    };
    if tools.len() > 64 {
        return Err(AppError::Validation(
            "PROVIDER_TOOL_SCHEMA_INVALID".to_owned(),
        ));
    }
    for tool in tools {
        let Value::Object(object) = tool else {
            return Err(AppError::Validation(
                "PROVIDER_TOOL_SCHEMA_INVALID".to_owned(),
            ));
        };
        let name = object
            .get("name")
            .or_else(|| {
                object
                    .get("function")
                    .and_then(Value::as_object)
                    .and_then(|f| f.get("name"))
            })
            .and_then(Value::as_str)
            .filter(|name| !name.is_empty() && name.len() <= 128)
            .ok_or_else(|| AppError::Validation("PROVIDER_TOOL_SCHEMA_INVALID".to_owned()))?;
        if !name
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'-' | b'.'))
        {
            return Err(AppError::Validation(
                "PROVIDER_TOOL_SCHEMA_INVALID".to_owned(),
            ));
        }
        if let Some(function) = object.get("function") {
            let Value::Object(function) = function else {
                return Err(AppError::Validation(
                    "PROVIDER_TOOL_SCHEMA_INVALID".to_owned(),
                ));
            };
            if let Some(parameters) = function.get("parameters") {
                validate_tool_parameters(parameters)?;
            }
        }
        if let Some(parameters) = object.get("parameters") {
            validate_tool_parameters(parameters)?;
        }
        if let Some(input_schema) = object.get("input_schema") {
            validate_tool_parameters(input_schema)?;
        }
    }
    Ok(())
}

fn validate_tool_parameters(value: &Value) -> Result<(), AppError> {
    let Value::Object(object) = value else {
        return Err(AppError::Validation(
            "PROVIDER_TOOL_SCHEMA_INVALID".to_owned(),
        ));
    };
    if object.get("type").and_then(Value::as_str) != Some("object") {
        return Err(AppError::Validation(
            "PROVIDER_TOOL_SCHEMA_INVALID".to_owned(),
        ));
    }
    if object.len() > 12 {
        return Err(AppError::Validation(
            "PROVIDER_TOOL_SCHEMA_INVALID".to_owned(),
        ));
    }
    Ok(())
}

fn parse_deadline(rfc3339: &str) -> Option<u64> {
    chrono::DateTime::parse_from_rfc3339(rfc3339)
        .ok()
        .map(|dt| {
            let now = chrono::Utc::now();
            let dur = dt.signed_duration_since(now);
            dur.num_seconds()
        })
        .filter(|seconds| (1..=600).contains(seconds))
        .map(|seconds| seconds as u64)
}

/// Register all reverse handlers into a ReverseMethodTable.
pub fn register_reverse_handlers(
    table: &mut ReverseMethodTable,
    http_broker: Arc<HttpBroker>,
    credential_store: Arc<CredentialStore>,
    grant_store: Arc<GrantStore>,
    receipt_store: Arc<ReceiptStore>,
    process_supervisor: Arc<ProcessSupervisor>,
) -> Arc<ReverseBroker> {
    table.register(
        "system.heartbeat",
        Arc::new(|params| {
            Box::pin(async move {
                if !params.is_object() {
                    return Err(IpcError::Internal("HEARTBEAT_PARAMS_INVALID".to_owned()));
                }
                Ok(serde_json::json!({"accepted": true}))
            })
        }),
    );
    let broker = Arc::new(ReverseBroker::new(http_broker, credential_store));
    let broker_clone = broker.clone();
    table.register(
        "credential.http.start",
        Arc::new(move |params| {
            let broker = broker_clone.clone();
            Box::pin(async move {
                let request: CredentialHttpStart = serde_json::from_value(params)
                    .map_err(|_| IpcError::Internal("RPC_PARAMS_INVALID".to_owned()))?;
                let result = broker.handle_credential_http_start(request).await;
                result.map_err(ipc_from_app_error)
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
                    .map_err(|_| IpcError::Internal("RPC_PARAMS_INVALID".to_owned()))?;
                let result = broker.handle_credential_http_cancel(request).await;
                result.map_err(ipc_from_app_error)
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
                    .map_err(|_| IpcError::Internal("RPC_PARAMS_INVALID".to_owned()))?;
                let result = broker.handle_credential_probe(request).await;
                result.map_err(ipc_from_app_error)
            })
        }),
    );
    let grant_store_clone = grant_store.clone();
    let receipt_store_clone = receipt_store.clone();
    table.register(
        "host.externalWrite.execute",
        Arc::new(move |params| {
            let grant_store = grant_store_clone.clone();
            let receipt_store = receipt_store_clone.clone();
            Box::pin(async move {
                let request: ExternalWriteRequest = serde_json::from_value(params)
                    .map_err(|_| IpcError::Internal("RPC_PARAMS_INVALID".to_owned()))?;
                handle_external_write_execute(request, &grant_store, &receipt_store)
                    .await
                    .map(|response| serde_json::to_value(response).unwrap_or(Value::Null))
                    .map_err(ipc_from_app_error)
            })
        }),
    );
    let supervisor = process_supervisor.clone();
    table.register(
        "runtime.process.start",
        Arc::new(move |params| {
            let supervisor = supervisor.clone();
            Box::pin(async move {
                let request: StartProcessRequest = serde_json::from_value(params)
                    .map_err(|_| IpcError::Internal("RPC_PARAMS_INVALID".to_owned()))?;
                supervisor.start(request).await.map_err(ipc_from_app_error)
            })
        }),
    );
    let supervisor = process_supervisor.clone();
    table.register(
        "runtime.process.cancel",
        Arc::new(move |params| {
            let supervisor = supervisor.clone();
            Box::pin(async move {
                let request: CancelProcessRequest = serde_json::from_value(params)
                    .map_err(|_| IpcError::Internal("RPC_PARAMS_INVALID".to_owned()))?;
                supervisor.cancel(request).await.map_err(ipc_from_app_error)
            })
        }),
    );
    let supervisor = process_supervisor.clone();
    table.register(
        "runtime.process.status",
        Arc::new(move |params| {
            let supervisor = supervisor.clone();
            Box::pin(async move {
                let request: ProcessRequest = serde_json::from_value(params)
                    .map_err(|_| IpcError::Internal("RPC_PARAMS_INVALID".to_owned()))?;
                supervisor
                    .status(request.process_id, request.run_id)
                    .await
                    .map_err(ipc_from_app_error)
            })
        }),
    );
    broker
}

/// Convert application failures at the reverse-RPC boundary to a stable,
/// non-sensitive code.  Provider URLs, OS errors and filesystem paths must
/// never cross the authenticated IPC boundary; the Sidecar only needs the
/// documented domain code to select its recovery path.
fn ipc_from_app_error(error: AppError) -> IpcError {
    let (fallback, message) = match error {
        AppError::Sidecar(message) => ("SIDECAR_ERROR", message),
        AppError::Auth(message) => ("AUTH_ERROR", message),
        AppError::Unauthorized(message) => ("UNAUTHORIZED", message),
        AppError::Validation(message) => ("VALIDATION_ERROR", message),
        AppError::NotFound(message) => ("NOT_FOUND", message),
        AppError::Network(message) => ("NETWORK_ERROR", message),
        AppError::Storage(message) => ("STORAGE_ERROR", message),
        AppError::Security(message) => ("SECURITY_ERROR", message),
        AppError::Internal(message) => ("INTERNAL_ERROR", message),
        AppError::Io(message) => ("IO_ERROR", message),
        AppError::Cancelled(message) => ("CANCELLED", message),
        AppError::ExternalOpen(message) => ("EXTERNAL_OPEN_ERROR", message),
        AppError::NotSupported(message) => ("NOT_SUPPORTED", message),
    };
    IpcError::Internal(stable_error_code(&message, fallback))
}

fn stable_error_code(message: &str, fallback: &str) -> String {
    let candidate = message
        .split(|character: char| character == ':' || character.is_whitespace())
        .next()
        .unwrap_or_default();
    if !candidate.is_empty()
        && candidate.len() <= 64
        && candidate
            .bytes()
            .all(|byte| byte.is_ascii_uppercase() || byte.is_ascii_digit() || byte == b'_')
    {
        candidate.to_owned()
    } else {
        fallback.to_owned()
    }
}

/// Allowed reverse methods from Sidecar to Rust
pub const ALLOWED_REVERSE_METHODS: &[&str] = &[
    "system.heartbeat",
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
    fn provider_deadline_is_fail_closed_and_bounded() {
        let valid = (chrono::Utc::now() + chrono::Duration::seconds(120)).to_rfc3339();
        let valid_seconds = parse_deadline(&valid).expect("future deadline accepted");
        assert!((118..=120).contains(&valid_seconds));
        let expired = (chrono::Utc::now() - chrono::Duration::seconds(1)).to_rfc3339();
        assert_eq!(parse_deadline(&expired), None);
        let too_far = (chrono::Utc::now() + chrono::Duration::seconds(1200)).to_rfc3339();
        assert_eq!(parse_deadline(&too_far), None);
        assert_eq!(parse_deadline("not-a-date"), None);
    }

    #[test]
    fn external_write_request_serialization_roundtrip() {
        let req = ExternalWriteRequest {
            approval_id: Uuid::new_v4(),
            workspace_grant_id: Uuid::new_v4(),
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
