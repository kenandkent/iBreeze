use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Arc;

use serde::{Deserialize, Serialize};
use serde_json::Value;
use tokio::sync::{oneshot, RwLock};
use uuid::Uuid;

use crate::broker::credential_index::{CredentialIndexStore, CredentialState};
use crate::broker::snapshot_authorization::{
    canonical_json, SnapshotAuthorizationStore, SnapshotRouteRole,
};
use crate::broker::{http::MAX_RETRIES, CredentialStore, HttpBroker};
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

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ProviderProtocol {
    OpenaiResponses,
    AnthropicMessages,
    OpenaiChatCompletions,
}

impl ProviderProtocol {
    pub(crate) fn as_str(&self) -> &'static str {
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
    pub routing_tier: u8,
    pub quality_prior: f64,
    pub tool_reliability_prior: f64,
    pub latency_prior_ms: u64,
    pub model_family: String,
    pub model_vendor: String,
    pub architecture_class: String,
    pub supports_reasoning: bool,
    pub reasoning_levels: Vec<String>,
    pub input_price_microusd_per_million: u64,
    pub output_price_microusd_per_million: u64,
    pub routing_enabled: bool,
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
    #[serde(default)]
    pub execution_snapshot_id: Option<Uuid>,
    #[serde(default)]
    pub route_decision_id: Option<Uuid>,
    #[serde(default)]
    pub route_attempt_id: Option<Uuid>,
    #[serde(default)]
    pub candidate_id: Option<Uuid>,
    #[serde(default)]
    pub route_role: Option<SnapshotRouteRole>,
    pub credential_ref: Uuid,
    #[serde(default = "default_secret_version")]
    pub credential_secret_version: u64,
    pub provider_release_id: Uuid,
    pub model_binding_id: Uuid,
    pub operation: ProviderOperation,
    pub request: Value,
    pub deadline_at: String,
}

fn default_secret_version() -> u64 {
    1
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

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CredentialDescribe {
    pub credential_ref: Uuid,
    pub provider_release_id: Uuid,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SnapshotRegister {
    pub execution_snapshot_id: Uuid,
    pub run_id: Uuid,
    pub candidate_bindings_json: String,
    pub candidate_bindings_sha256: String,
    pub run_deadline_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DecisionRegister {
    pub route_decision_id: Uuid,
    pub run_id: Uuid,
    pub execution_snapshot_id: Uuid,
    pub turn_index: u32,
    pub selections: Vec<DecisionSelection>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DecisionSelection {
    pub candidate_id: Uuid,
    pub role: SnapshotRouteRole,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SnapshotRevoke {
    pub run_id: Uuid,
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
    profile_root: Arc<RwLock<Option<PathBuf>>>,
    catalog: Arc<RwLock<Option<CatalogSnapshot>>>,
    pub snapshot_authorization: SnapshotAuthorizationStore,
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
            profile_root: Arc::new(RwLock::new(None)),
            catalog: Arc::new(RwLock::new(None)),
            snapshot_authorization: SnapshotAuthorizationStore::default(),
        }
    }

    pub async fn bind_client(&self, client: Option<Arc<SidecarClient>>) {
        *self.notification_client.write().await = client.map(|value| Arc::downgrade(&value));
    }

    pub async fn bind_profile(&self, profile_directory_id: Option<String>) {
        *self.profile_directory_id.write().await = profile_directory_id;
    }

    pub async fn bind_profile_root(&self, profile_root: Option<PathBuf>) {
        *self.profile_root.write().await = profile_root;
    }

    pub async fn bind_catalog(&self, snapshot: Option<CatalogSnapshot>) {
        *self.catalog.write().await = snapshot;
    }

    pub async fn validate_credential_auth_type(
        &self,
        provider_release_id: Uuid,
        auth_type: &str,
    ) -> Result<(), AppError> {
        let catalog = self.catalog.read().await;
        let provider = catalog
            .as_ref()
            .and_then(|snapshot| {
                snapshot
                    .providers
                    .iter()
                    .find(|provider| provider.provider_release_id == provider_release_id)
            })
            .ok_or_else(|| AppError::Validation("CATALOG_PROVIDER_NOT_FOUND".to_owned()))?;
        let expected = match provider.auth_scheme.as_str() {
            "bearer" => "bearer",
            "x-api-key" => "x_api_key",
            _ => {
                return Err(AppError::Validation(
                    "CREDENTIAL_AUTH_TYPE_INVALID".to_owned(),
                ))
            }
        };
        if expected != auth_type {
            return Err(AppError::Validation(
                "CREDENTIAL_AUTH_TYPE_MISMATCH".to_owned(),
            ));
        }
        Ok(())
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
        self.snapshot_authorization.clear().await;
        count
    }

    pub async fn handle_snapshot_register(
        &self,
        request: SnapshotRegister,
    ) -> Result<Value, AppError> {
        let deadline = chrono::DateTime::parse_from_rfc3339(&request.run_deadline_at)
            .map_err(|_| AppError::Validation("ROUTING_SNAPSHOT_INVALID".to_owned()))?
            .with_timezone(&chrono::Utc);
        self.validate_snapshot_credentials(&request.candidate_bindings_json)
            .await?;
        let snapshot = self
            .snapshot_authorization
            .register_snapshot(
                request.execution_snapshot_id,
                request.run_id,
                request.candidate_bindings_json,
                request.candidate_bindings_sha256,
                deadline,
            )
            .await?;
        Ok(
            serde_json::json!({"execution_snapshot_id": snapshot.execution_snapshot_id, "run_id": snapshot.run_id, "authorized": true, "run_deadline_at": snapshot.run_deadline_at.to_rfc3339()}),
        )
    }

    async fn validate_snapshot_credentials(
        &self,
        candidate_bindings_json: &str,
    ) -> Result<(), AppError> {
        let profile_root = self
            .profile_root
            .read()
            .await
            .clone()
            .ok_or_else(|| AppError::Auth("PROFILE_NOT_OPEN".to_owned()))?;
        let index = CredentialIndexStore::new(profile_root).load()?;
        let candidates = crate::broker::snapshot_authorization::parse_authorized_candidates(
            candidate_bindings_json,
        )?;
        for candidate in candidates {
            let metadata = index
                .credentials
                .iter()
                .find(|item| item.credential_ref == candidate.credential_ref)
                .ok_or_else(|| AppError::NotFound("CREDENTIAL_MISSING".to_owned()))?;
            if metadata.provider_release_id != candidate.provider_release_id {
                return Err(AppError::Validation(
                    "CREDENTIAL_PROVIDER_MISMATCH".to_owned(),
                ));
            }
            if !matches!(metadata.state, CredentialState::Ready) {
                return Err(AppError::Validation(
                    match metadata.state {
                        CredentialState::Deleting => "CREDENTIAL_IN_USE",
                        _ => "CREDENTIAL_NOT_READY",
                    }
                    .to_owned(),
                ));
            }
            if metadata.active_secret_version != Some(candidate.credential_secret_version) {
                return Err(AppError::Validation(
                    "CREDENTIAL_VERSION_MISMATCH".to_owned(),
                ));
            }
        }
        Ok(())
    }

    pub async fn handle_decision_register(
        &self,
        request: DecisionRegister,
    ) -> Result<Value, AppError> {
        let selections = request
            .selections
            .into_iter()
            .map(|item| (item.candidate_id, item.role))
            .collect();
        self.snapshot_authorization
            .register_decision(
                request.route_decision_id,
                request.run_id,
                request.execution_snapshot_id,
                selections,
            )
            .await?;
        Ok(serde_json::json!({"route_decision_id": request.route_decision_id, "registered": true}))
    }

    pub async fn handle_snapshot_revoke(&self, request: SnapshotRevoke) -> Result<Value, AppError> {
        self.snapshot_authorization.revoke_run(request.run_id).await;
        Ok(serde_json::json!({"run_id": request.run_id, "revoked": true}))
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
        validate_route_metadata_presence(
            request.execution_snapshot_id,
            request.route_decision_id,
            request.route_attempt_id,
            request.candidate_id,
            request.route_role.as_ref(),
        )?;
        let deadline_s = parse_deadline(&request.deadline_at)
            .ok_or_else(|| AppError::Validation("PROVIDER_DEADLINE_INVALID".to_owned()))?;
        let request_deadline = chrono::DateTime::parse_from_rfc3339(&request.deadline_at)
            .map_err(|_| AppError::Validation("PROVIDER_DEADLINE_INVALID".to_owned()))?
            .with_timezone(&chrono::Utc);
        let profile_directory_id = self
            .profile_directory_id
            .read()
            .await
            .clone()
            .ok_or_else(|| AppError::Auth("PROFILE_NOT_OPEN".to_owned()))?;
        let mut expected_request_defaults_sha256: Option<String> = None;
        let mut expected_provider_protocol: Option<ProviderProtocol> = None;
        if let (
            Some(snapshot_id),
            Some(decision_id),
            Some(attempt_id),
            Some(candidate_id),
            Some(role),
        ) = (
            request.execution_snapshot_id,
            request.route_decision_id,
            request.route_attempt_id,
            request.candidate_id,
            request.route_role.clone(),
        ) {
            let authorized = self
                .snapshot_authorization
                .authorize_attempt(
                    crate::broker::snapshot_authorization::AuthorizeAttemptRequest {
                        attempt_id,
                        decision_id,
                        run_id: request.run_id,
                        snapshot_id,
                        candidate_id,
                        role,
                        now: chrono::Utc::now(),
                    },
                )
                .await?;
            self.snapshot_authorization
                .validate_request_deadline(snapshot_id, request.run_id, request_deadline)
                .await?;
            if authorized.provider_release_id != request.provider_release_id
                || authorized.model_binding_id != request.model_binding_id
                || authorized.credential_ref != request.credential_ref
                || authorized.credential_secret_version != request.credential_secret_version
            {
                return Err(AppError::Security(
                    "ROUTING_SNAPSHOT_NOT_AUTHORIZED".to_owned(),
                ));
            }
            expected_request_defaults_sha256 = authorized.request_defaults_sha256.clone();
            expected_provider_protocol = authorized.provider_protocol.clone();
            if let Some(existing_request_id) =
                self.snapshot_authorization.bound_request(attempt_id).await
            {
                if let Some(terminal) = self
                    .terminal_requests
                    .read()
                    .await
                    .get(&existing_request_id)
                    .cloned()
                {
                    return Ok(terminal);
                }
                return Ok(serde_json::json!({
                    "request_id": existing_request_id,
                    "accepted": true,
                    "stream": true,
                    "replayed": true,
                }));
            }
        }
        let provider = self
            .resolve_provider(request.provider_release_id, request.model_binding_id)
            .await?;
        if let Some(expected) = expected_provider_protocol.as_ref() {
            if expected.as_str() != provider.protocol.as_str() {
                return Err(AppError::Security(
                    "ROUTING_SNAPSHOT_NOT_AUTHORIZED".to_owned(),
                ));
            }
        }
        if let Some(expected) = expected_request_defaults_sha256.as_deref() {
            if expected != provider.request_defaults_sha256 {
                return Err(AppError::Security(
                    "ROUTING_SNAPSHOT_NOT_AUTHORIZED".to_owned(),
                ));
            }
        }
        let credential = self.credential_store.load_keychain_credential_version(
            &profile_directory_id,
            request.credential_ref,
            request.credential_secret_version,
        )?;
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
                provider.protocol.expected_path(),
                request_body,
                deadline_s,
                // Model-level retry/fallback is owned by Sidecar.  A
                // RouteAttempt must correspond to exactly one physical HTTP
                // request, so the Broker must not retry this operation.
                0,
            )
            .await?;
        self.cancel_senders
            .write()
            .await
            .insert(request_id, (request.run_id, cancel_tx));
        if let Some(attempt_id) = request.route_attempt_id {
            self.snapshot_authorization
                .bind_request(attempt_id, request_id)
                .await?;
        }
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
                // Credential Probe is outside RouteAttempt accounting and may
                // use the Broker's independent transient retry budget.
                MAX_RETRIES,
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

    pub async fn handle_credential_describe(
        &self,
        request: CredentialDescribe,
    ) -> Result<Value, AppError> {
        let profile_root = self
            .profile_root
            .read()
            .await
            .clone()
            .ok_or_else(|| AppError::Auth("PROFILE_NOT_OPEN".to_owned()))?;
        let index = CredentialIndexStore::new(profile_root).load()?;
        let item = index
            .credentials
            .into_iter()
            .find(|item| item.credential_ref == request.credential_ref)
            .ok_or_else(|| AppError::NotFound("CREDENTIAL_NOT_FOUND".to_owned()))?;
        if item.provider_release_id != request.provider_release_id {
            return Err(AppError::Validation(
                "CREDENTIAL_PROVIDER_MISMATCH".to_owned(),
            ));
        }
        Ok(serde_json::json!({
            "credential_ref": item.credential_ref,
            "provider_release_id": item.provider_release_id,
            "auth_type": item.auth_type,
            "state": item.state,
            "metadata_version": item.metadata_version,
            "active_secret_version": item.active_secret_version,
        }))
    }

    /// Public credential management owns only metadata and the expected
    /// version.  Provider/model selection is resolved from the signed Catalog
    /// here so the Tauri command cannot probe an arbitrary URL or model.
    pub async fn probe_credential_ref(
        &self,
        credential_ref: Uuid,
        provider_release_id: Uuid,
    ) -> Result<Value, AppError> {
        let catalog = self.catalog.read().await.clone();
        let snapshot =
            catalog.ok_or_else(|| AppError::Validation("CATALOG_NOT_AVAILABLE".to_owned()))?;
        let provider = snapshot
            .providers
            .iter()
            .find(|item| item.provider_release_id == provider_release_id)
            .ok_or_else(|| AppError::Validation("CATALOG_PROVIDER_NOT_FOUND".to_owned()))?;
        let binding = provider
            .model_bindings
            .first()
            .ok_or_else(|| AppError::Validation("CATALOG_MODEL_BINDING_NOT_FOUND".to_owned()))?;
        self.handle_credential_probe(CredentialProbe {
            credential_ref,
            provider_release_id,
            model_binding_id: binding.binding_id,
        })
        .await
    }

    async fn resolve_provider(
        &self,
        provider_release_id: Uuid,
        model_binding_id: Uuid,
    ) -> Result<ResolvedProvider, AppError> {
        let catalog = self.catalog.read().await;
        let snapshot = catalog
            .as_ref()
            .ok_or_else(|| AppError::Validation("CATALOG_NOT_AVAILABLE".to_owned()))?;
        let provider = resolve_provider(snapshot, provider_release_id, model_binding_id)?;
        Ok(provider)
    }
}

fn validate_route_metadata_presence(
    execution_snapshot_id: Option<Uuid>,
    route_decision_id: Option<Uuid>,
    route_attempt_id: Option<Uuid>,
    candidate_id: Option<Uuid>,
    route_role: Option<&SnapshotRouteRole>,
) -> Result<(), AppError> {
    let present = [
        execution_snapshot_id.is_some(),
        route_decision_id.is_some(),
        route_attempt_id.is_some(),
        candidate_id.is_some(),
        route_role.is_some(),
    ];
    let any = present.iter().any(|value| *value);
    let complete = present.iter().all(|value| *value);
    if any && !complete {
        return Err(AppError::Security(
            "ROUTING_SNAPSHOT_NOT_AUTHORIZED".to_owned(),
        ));
    }
    Ok(())
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
    request_defaults_sha256: String,
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
        request_defaults_sha256: json_sha256(&binding.request_defaults)?,
        request_defaults: binding.request_defaults.clone(),
        protocol: provider.protocol.clone(),
    })
}

fn json_sha256(value: &Value) -> Result<String, AppError> {
    use sha2::{Digest, Sha256};

    let bytes = canonical_json(value)
        .map_err(|_| AppError::Validation("CATALOG_REQUEST_DEFAULTS_INVALID".to_owned()))?;
    Ok(format!("{:x}", Sha256::digest(bytes.as_bytes())))
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
        "relative_path",
        "protocol",
        "provider_protocol",
        "endpoint",
        "headers",
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
        "routing.snapshot.register",
        Arc::new(move |params| {
            let broker = broker_clone.clone();
            Box::pin(async move {
                let request: SnapshotRegister = serde_json::from_value(params)
                    .map_err(|_| IpcError::Internal("RPC_PARAMS_INVALID".to_owned()))?;
                broker
                    .handle_snapshot_register(request)
                    .await
                    .map_err(ipc_from_app_error)
            })
        }),
    );
    let broker_clone = broker.clone();
    table.register(
        "routing.decision.register",
        Arc::new(move |params| {
            let broker = broker_clone.clone();
            Box::pin(async move {
                let request: DecisionRegister = serde_json::from_value(params)
                    .map_err(|_| IpcError::Internal("RPC_PARAMS_INVALID".to_owned()))?;
                broker
                    .handle_decision_register(request)
                    .await
                    .map_err(ipc_from_app_error)
            })
        }),
    );
    let broker_clone = broker.clone();
    table.register(
        "routing.snapshot.revoke",
        Arc::new(move |params| {
            let broker = broker_clone.clone();
            Box::pin(async move {
                let request: SnapshotRevoke = serde_json::from_value(params)
                    .map_err(|_| IpcError::Internal("RPC_PARAMS_INVALID".to_owned()))?;
                broker
                    .handle_snapshot_revoke(request)
                    .await
                    .map_err(ipc_from_app_error)
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
        "credential.describe",
        Arc::new(move |params| {
            let broker = broker_clone.clone();
            Box::pin(async move {
                let request: CredentialDescribe = serde_json::from_value(params)
                    .map_err(|_| IpcError::Internal("RPC_PARAMS_INVALID".to_owned()))?;
                broker
                    .handle_credential_describe(request)
                    .await
                    .map_err(ipc_from_app_error)
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
        AppError::Conflict(message) => ("CONFLICT", message),
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
    "routing.snapshot.register",
    "routing.decision.register",
    "routing.snapshot.revoke",
    "credential.http.start",
    "credential.http.cancel",
    "credential.probe",
    "credential.describe",
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
        assert!(validate_reverse_method("credential.describe").is_ok());
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
    fn provider_request_rejects_catalog_owned_transport_fields() {
        let provider = ResolvedProvider {
            base_url: "https://provider.example".to_owned(),
            auth_scheme: "bearer".to_owned(),
            model_name: "model-a".to_owned(),
            request_defaults: serde_json::json!({}),
            request_defaults_sha256: json_sha256(&serde_json::json!({})).expect("hash"),
            protocol: ProviderProtocol::OpenaiResponses,
        };
        for field in [
            "url",
            "relative_path",
            "protocol",
            "provider_protocol",
            "endpoint",
            "headers",
            "authorization",
            "stream",
        ] {
            let request = serde_json::json!({field: "attacker-controlled"});
            let error = prepare_provider_request(&request, &provider).expect_err(field);
            assert_eq!(
                error.to_string(),
                "Validation error: PROVIDER_REQUEST_FIELD_FORBIDDEN"
            );
        }
        let model_override = serde_json::json!({"model": "attacker-model"});
        let error = prepare_provider_request(&model_override, &provider).expect_err("model");
        assert_eq!(
            error.to_string(),
            "Validation error: PROVIDER_MODEL_OVERRIDE_FORBIDDEN"
        );
    }

    #[test]
    fn routed_http_request_requires_all_snapshot_metadata() {
        let snapshot = Uuid::new_v4();
        let decision = Uuid::new_v4();
        let attempt = Uuid::new_v4();
        let candidate = Uuid::new_v4();
        let role = SnapshotRouteRole::Single;
        assert!(validate_route_metadata_presence(None, None, None, None, None).is_ok());
        assert!(validate_route_metadata_presence(
            Some(snapshot),
            Some(decision),
            Some(attempt),
            Some(candidate),
            Some(&role),
        )
        .is_ok());
        let error = validate_route_metadata_presence(
            Some(snapshot),
            Some(decision),
            None,
            Some(candidate),
            Some(&role),
        )
        .expect_err("partial snapshot metadata must fail closed");
        assert_eq!(
            error.to_string(),
            "Security error: ROUTING_SNAPSHOT_NOT_AUTHORIZED"
        );
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
