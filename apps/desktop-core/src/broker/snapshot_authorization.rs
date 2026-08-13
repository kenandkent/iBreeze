//! In-memory authorization leases for immutable routing snapshots.
//!
//! The Sidecar supplies only a signed/canonical candidate snapshot.  Rust
//! retains the lease for the lifetime of the run and checks every physical
//! provider request against it before looking up credentials or starting HTTP.

use std::collections::{BTreeSet, HashMap};
use std::sync::Arc;

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use tokio::sync::RwLock;
use uuid::Uuid;

use crate::error::AppError;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, PartialOrd, Ord)]
#[serde(rename_all = "snake_case")]
pub enum SnapshotRouteRole {
    Single,
    Proposer,
    Aggregator,
    Fallback,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AuthorizedCandidate {
    pub candidate_id: Uuid,
    pub provider_release_id: Uuid,
    pub model_binding_id: Uuid,
    pub credential_ref: Uuid,
    #[serde(default = "default_secret_version")]
    pub credential_secret_version: u64,
    #[serde(default)]
    pub eligible_roles: BTreeSet<SnapshotRouteRole>,
    #[serde(default)]
    pub request_defaults_sha256: Option<String>,
    /// Present only in v2 snapshots.  Legacy fixed snapshots intentionally
    /// omit this field and let the signed Catalog provide the protocol.
    #[serde(default)]
    pub provider_protocol: Option<crate::rpc::reverse::ProviderProtocol>,
}

fn default_secret_version() -> u64 {
    1
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SnapshotAuthorization {
    pub execution_snapshot_id: Uuid,
    pub run_id: Uuid,
    pub candidate_bindings_json: String,
    pub candidate_bindings_sha256: String,
    pub candidates: Vec<AuthorizedCandidate>,
    pub run_deadline_at: DateTime<Utc>,
}

#[derive(Debug, Clone)]
pub struct DecisionAuthorization {
    pub run_id: Uuid,
    pub execution_snapshot_id: Uuid,
    pub selections: Vec<(Uuid, SnapshotRouteRole)>,
}

#[derive(Debug, Clone)]
pub struct AttemptAuthorization {
    pub run_id: Uuid,
    pub route_decision_id: Uuid,
    pub candidate_id: Uuid,
    pub role: SnapshotRouteRole,
    pub request_id: Option<Uuid>,
    pub terminal: bool,
}

#[derive(Debug, Clone)]
pub struct AuthorizeAttemptRequest {
    pub attempt_id: Uuid,
    pub decision_id: Uuid,
    pub run_id: Uuid,
    pub snapshot_id: Uuid,
    pub candidate_id: Uuid,
    pub role: SnapshotRouteRole,
    pub now: DateTime<Utc>,
}

#[derive(Clone, Default)]
pub struct SnapshotAuthorizationStore {
    snapshots: Arc<RwLock<HashMap<Uuid, SnapshotAuthorization>>>,
    decisions: Arc<RwLock<HashMap<Uuid, DecisionAuthorization>>>,
    attempts: Arc<RwLock<HashMap<Uuid, AttemptAuthorization>>>,
}

impl SnapshotAuthorizationStore {
    pub async fn validate_request_deadline(
        &self,
        snapshot_id: Uuid,
        run_id: Uuid,
        request_deadline: DateTime<Utc>,
    ) -> Result<(), AppError> {
        let snapshots = self.snapshots.read().await;
        let snapshot = snapshots
            .get(&snapshot_id)
            .ok_or_else(|| AppError::Security("ROUTING_SNAPSHOT_NOT_AUTHORIZED".to_owned()))?;
        if snapshot.run_id != run_id || request_deadline > snapshot.run_deadline_at {
            return Err(AppError::Security(
                "ROUTING_SNAPSHOT_NOT_AUTHORIZED".to_owned(),
            ));
        }
        Ok(())
    }

    pub async fn register_snapshot(
        &self,
        snapshot_id: Uuid,
        run_id: Uuid,
        candidate_bindings_json: String,
        candidate_bindings_sha256: String,
        run_deadline_at: DateTime<Utc>,
    ) -> Result<SnapshotAuthorization, AppError> {
        if sha256_hex(candidate_bindings_json.as_bytes()) != candidate_bindings_sha256 {
            return Err(AppError::Security(
                "ROUTING_SNAPSHOT_HASH_MISMATCH".to_owned(),
            ));
        }
        let raw: Value = serde_json::from_str(&candidate_bindings_json)
            .map_err(|_| AppError::Validation("ROUTING_SNAPSHOT_INVALID".to_owned()))?;
        if !raw.is_array() {
            return Err(AppError::Validation("ROUTING_SNAPSHOT_INVALID".to_owned()));
        }
        let canonical = canonical_json(&raw)?;
        if canonical != candidate_bindings_json {
            return Err(AppError::Validation("ROUTING_SNAPSHOT_INVALID".to_owned()));
        }
        let candidates = parse_authorized_candidates(&candidate_bindings_json)?;
        let mut candidate_ids = BTreeSet::new();
        if candidates.is_empty()
            || run_deadline_at <= Utc::now()
            || candidates
                .iter()
                .any(|candidate| !candidate_ids.insert(candidate.candidate_id))
        {
            return Err(AppError::Validation("ROUTING_SNAPSHOT_INVALID".to_owned()));
        }
        let authorization = SnapshotAuthorization {
            execution_snapshot_id: snapshot_id,
            run_id,
            candidate_bindings_json,
            candidate_bindings_sha256,
            candidates,
            run_deadline_at,
        };
        let mut snapshots = self.snapshots.write().await;
        if let Some(previous) = snapshots.get(&snapshot_id) {
            if previous.run_id == run_id
                && previous.candidate_bindings_sha256 == authorization.candidate_bindings_sha256
                && previous.run_deadline_at == authorization.run_deadline_at
            {
                return Ok(previous.clone());
            }
            return Err(AppError::Conflict("ROUTING_SNAPSHOT_CONFLICT".to_owned()));
        }
        snapshots.insert(snapshot_id, authorization.clone());
        Ok(authorization)
    }

    pub async fn register_decision(
        &self,
        decision_id: Uuid,
        run_id: Uuid,
        snapshot_id: Uuid,
        selections: Vec<(Uuid, SnapshotRouteRole)>,
    ) -> Result<(), AppError> {
        let snapshot = self
            .snapshots
            .read()
            .await
            .get(&snapshot_id)
            .cloned()
            .ok_or_else(|| AppError::Security("ROUTING_SNAPSHOT_NOT_AUTHORIZED".to_owned()))?;
        // A deployment may legally serve two different roles (for example a
        // proposer and the aggregator).  The immutable identity is the
        // candidate/role pair, not the candidate alone.
        let mut selected_pairs = BTreeSet::new();
        if snapshot.run_id != run_id
            || selections.is_empty()
            || selections
                .iter()
                .any(|pair| !selected_pairs.insert(pair.clone()))
            || selections.iter().any(|(candidate_id, role)| {
                snapshot
                    .candidates
                    .iter()
                    .find(|candidate| candidate.candidate_id == *candidate_id)
                    .map(|candidate| !candidate.eligible_roles.contains(role))
                    .unwrap_or(true)
            })
        {
            return Err(AppError::Security(
                "ROUTING_SNAPSHOT_NOT_AUTHORIZED".to_owned(),
            ));
        }
        let authorization = DecisionAuthorization {
            run_id,
            execution_snapshot_id: snapshot_id,
            selections,
        };
        let mut decisions = self.decisions.write().await;
        if let Some(previous) = decisions.get(&decision_id) {
            if previous.run_id == authorization.run_id
                && previous.execution_snapshot_id == authorization.execution_snapshot_id
                && previous.selections == authorization.selections
            {
                return Ok(());
            }
            return Err(AppError::Conflict("ROUTE_DECISION_CONFLICT".to_owned()));
        }
        decisions.insert(decision_id, authorization);
        Ok(())
    }

    pub async fn authorize_attempt(
        &self,
        request: AuthorizeAttemptRequest,
    ) -> Result<AuthorizedCandidate, AppError> {
        let AuthorizeAttemptRequest {
            attempt_id,
            decision_id,
            run_id,
            snapshot_id,
            candidate_id,
            role,
            now,
        } = request;
        let snapshot = self
            .snapshots
            .read()
            .await
            .get(&snapshot_id)
            .cloned()
            .ok_or_else(|| AppError::Security("ROUTING_SNAPSHOT_NOT_AUTHORIZED".to_owned()))?;
        if snapshot.run_id != run_id || snapshot.run_deadline_at < now {
            return Err(AppError::Security(
                "ROUTING_SNAPSHOT_NOT_AUTHORIZED".to_owned(),
            ));
        }
        let decision = self
            .decisions
            .read()
            .await
            .get(&decision_id)
            .cloned()
            .ok_or_else(|| AppError::Security("ROUTING_SNAPSHOT_NOT_AUTHORIZED".to_owned()))?;
        if decision.run_id != run_id
            || decision.execution_snapshot_id != snapshot_id
            || !decision.selections.contains(&(candidate_id, role.clone()))
        {
            return Err(AppError::Security(
                "ROUTING_SNAPSHOT_NOT_AUTHORIZED".to_owned(),
            ));
        }
        let candidate = snapshot
            .candidates
            .iter()
            .find(|item| item.candidate_id == candidate_id && item.eligible_roles.contains(&role))
            .cloned()
            .ok_or_else(|| AppError::Security("ROUTING_SNAPSHOT_NOT_AUTHORIZED".to_owned()))?;
        let mut attempts = self.attempts.write().await;
        if let Some(previous) = attempts.get(&attempt_id) {
            if previous.run_id == run_id
                && previous.route_decision_id == decision_id
                && previous.candidate_id == candidate_id
                && previous.role == role
            {
                return Ok(candidate);
            }
            return Err(AppError::Conflict("ROUTE_ATTEMPT_CONFLICT".to_owned()));
        }
        attempts.insert(
            attempt_id,
            AttemptAuthorization {
                run_id,
                route_decision_id: decision_id,
                candidate_id,
                role,
                request_id: None,
                terminal: false,
            },
        );
        Ok(candidate)
    }

    pub async fn bind_request(&self, attempt_id: Uuid, request_id: Uuid) -> Result<(), AppError> {
        let mut attempts = self.attempts.write().await;
        let attempt = attempts
            .get_mut(&attempt_id)
            .ok_or_else(|| AppError::NotFound("ROUTE_ATTEMPT_NOT_FOUND".to_owned()))?;
        if attempt.request_id.is_some() && attempt.request_id != Some(request_id) {
            return Err(AppError::Conflict("ROUTE_ATTEMPT_CONFLICT".to_owned()));
        }
        attempt.request_id = Some(request_id);
        Ok(())
    }

    pub async fn bound_request(&self, attempt_id: Uuid) -> Option<Uuid> {
        self.attempts
            .read()
            .await
            .get(&attempt_id)
            .and_then(|attempt| attempt.request_id)
    }

    pub async fn revoke_run(&self, run_id: Uuid) {
        self.snapshots
            .write()
            .await
            .retain(|_, value| value.run_id != run_id);
        let decision_ids: BTreeSet<Uuid> = self
            .decisions
            .read()
            .await
            .iter()
            .filter_map(|(id, value)| (value.run_id == run_id).then_some(*id))
            .collect();
        self.decisions
            .write()
            .await
            .retain(|_, value| value.run_id != run_id);
        self.attempts.write().await.retain(|_, value| {
            value.run_id != run_id && !decision_ids.contains(&value.route_decision_id)
        });
    }

    pub async fn clear(&self) {
        self.snapshots.write().await.clear();
        self.decisions.write().await.clear();
        self.attempts.write().await.clear();
    }

    pub async fn active_for_credential(&self, credential_ref: Uuid) -> usize {
        let snapshots = self.snapshots.read().await;
        let now = Utc::now();
        snapshots
            .values()
            .filter(|snapshot| {
                snapshot.run_deadline_at > now
                    && snapshot
                        .candidates
                        .iter()
                        .any(|candidate| candidate.credential_ref == credential_ref)
            })
            .count()
    }
}

fn sha256_hex(bytes: &[u8]) -> String {
    use sha2::{Digest, Sha256};
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    format!("{:x}", hasher.finalize())
}

/// RFC 8785-compatible serialization for the routing JSON subset.
/// Object keys are sorted by UTF-16 code units, matching the Sidecar
/// canonicalizer. Routing schemas do not permit floating-point values; the
/// Catalog defaults use the stable textual representation emitted by
/// `serde_json::Number`.
pub(crate) fn canonical_json(value: &Value) -> Result<String, AppError> {
    fn write_value(value: &Value, output: &mut String) -> Result<(), AppError> {
        match value {
            Value::Null => output.push_str("null"),
            Value::Bool(value) => output.push_str(if *value { "true" } else { "false" }),
            Value::Number(number) => output.push_str(&number.to_string()),
            Value::String(value) => output.push_str(
                &serde_json::to_string(value)
                    .map_err(|_| AppError::Validation("ROUTING_SNAPSHOT_INVALID".to_owned()))?,
            ),
            Value::Array(values) => {
                output.push('[');
                for (index, item) in values.iter().enumerate() {
                    if index > 0 {
                        output.push(',');
                    }
                    write_value(item, output)?;
                }
                output.push(']');
            }
            Value::Object(values) => {
                let mut entries: Vec<(&String, &Value)> = values.iter().collect();
                entries.sort_by_key(|(key, _)| key.encode_utf16().collect::<Vec<_>>());
                output.push('{');
                for (index, (key, item)) in entries.into_iter().enumerate() {
                    if index > 0 {
                        output.push(',');
                    }
                    output.push_str(&serde_json::to_string(key).map_err(|_| {
                        AppError::Validation("ROUTING_SNAPSHOT_INVALID".to_owned())
                    })?);
                    output.push(':');
                    write_value(item, output)?;
                }
                output.push('}');
            }
        }
        Ok(())
    }

    let mut output = String::new();
    write_value(value, &mut output)?;
    Ok(output)
}

pub(crate) fn parse_authorized_candidates(
    candidate_bindings_json: &str,
) -> Result<Vec<AuthorizedCandidate>, AppError> {
    let raw: Value = serde_json::from_str(candidate_bindings_json)
        .map_err(|_| AppError::Validation("ROUTING_SNAPSHOT_INVALID".to_owned()))?;
    let array = raw
        .as_array()
        .ok_or_else(|| AppError::Validation("ROUTING_SNAPSHOT_INVALID".to_owned()))?;
    array.iter().map(authorized_candidate_from_value).collect()
}

/// Extract only the authorization fields from the full v2 candidate binding.
/// The Sidecar registers the exact canonical v2 bytes (including model
/// metadata) so the hash remains a snapshot hash, while Rust keeps a minimal
/// in-memory lease.  The legacy minimal projection is accepted during the
/// fixed compatibility window and follows the same field validation.
fn authorized_candidate_from_value(value: &Value) -> Result<AuthorizedCandidate, AppError> {
    let object = value
        .as_object()
        .ok_or_else(|| AppError::Validation("ROUTING_SNAPSHOT_INVALID".to_owned()))?;
    const ALLOWED_KEYS: &[&str] = &[
        "candidate_id",
        "provider_release_id",
        "provider_key",
        "provider_protocol",
        "model_binding_id",
        "model_id",
        "provider_model_name",
        "credential_ref",
        "credential_secret_version",
        "context_window",
        "max_output_tokens",
        "supports_tools",
        "supports_streaming",
        "supports_vision",
        "routing_tier",
        "quality_prior",
        "tool_reliability_prior",
        "latency_prior_ms",
        "model_family",
        "model_vendor",
        "architecture_class",
        "supports_reasoning",
        "reasoning_levels",
        "input_price_microusd_per_million",
        "output_price_microusd_per_million",
        "routing_enabled",
        "eligible_roles",
        "request_defaults_sha256",
    ];
    if object
        .keys()
        .any(|key| !ALLOWED_KEYS.contains(&key.as_str()))
    {
        return Err(AppError::Validation("ROUTING_SNAPSHOT_INVALID".to_owned()));
    }
    let get_uuid = |key: &str| {
        object
            .get(key)
            .and_then(Value::as_str)
            .and_then(|raw| Uuid::parse_str(raw).ok())
            .ok_or_else(|| AppError::Validation("ROUTING_SNAPSHOT_INVALID".to_owned()))
    };
    let credential_secret_version = object
        .get("credential_secret_version")
        .and_then(Value::as_u64)
        .unwrap_or(1);
    let eligible_roles = object
        .get("eligible_roles")
        .and_then(Value::as_array)
        .ok_or_else(|| AppError::Validation("ROUTING_SNAPSHOT_INVALID".to_owned()))?
        .iter()
        .cloned()
        .map(|role| {
            serde_json::from_value(role)
                .map_err(|_| AppError::Validation("ROUTING_SNAPSHOT_INVALID".to_owned()))
        })
        .collect::<Result<BTreeSet<_>, _>>()?;
    let request_defaults_sha256 = match object.get("request_defaults_sha256") {
        None => None,
        Some(Value::String(value)) if value.is_empty() => None,
        Some(Value::String(value)) if is_sha256_hex(value) => Some(value.to_owned()),
        _ => return Err(AppError::Validation("ROUTING_SNAPSHOT_INVALID".to_owned())),
    };
    let is_v2 = object.keys().any(|key| {
        matches!(
            key.as_str(),
            "provider_key"
                | "provider_protocol"
                | "model_id"
                | "provider_model_name"
                | "context_window"
        )
    });
    let provider_protocol = match object.get("provider_protocol") {
        None if !is_v2 => None,
        Some(value) => Some(
            serde_json::from_value(value.clone())
                .map_err(|_| AppError::Validation("ROUTING_SNAPSHOT_INVALID".to_owned()))?,
        ),
        None => return Err(AppError::Validation("ROUTING_SNAPSHOT_INVALID".to_owned())),
    };
    if is_v2 && (request_defaults_sha256.is_none() || provider_protocol.is_none()) {
        return Err(AppError::Validation("ROUTING_SNAPSHOT_INVALID".to_owned()));
    }
    Ok(AuthorizedCandidate {
        candidate_id: get_uuid("candidate_id")?,
        provider_release_id: get_uuid("provider_release_id")?,
        model_binding_id: get_uuid("model_binding_id")?,
        credential_ref: get_uuid("credential_ref")?,
        credential_secret_version,
        eligible_roles,
        request_defaults_sha256,
        provider_protocol,
    })
}

fn is_sha256_hex(value: &str) -> bool {
    value.len() == 64 && value.bytes().all(|byte| byte.is_ascii_hexdigit())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn candidate(candidate_id: Uuid) -> Value {
        serde_json::json!({
            "candidate_id": candidate_id,
            "provider_release_id": Uuid::new_v4(),
            "model_binding_id": Uuid::new_v4(),
            "credential_ref": Uuid::new_v4(),
            "credential_secret_version": 1,
            "eligible_roles": ["single", "fallback"],
            "request_defaults_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        })
    }

    #[test]
    fn full_v2_candidate_object_is_accepted_by_authorization_parser() {
        let mut value = candidate(Uuid::new_v4());
        value["provider_key"] = Value::String("provider".to_owned());
        value["provider_protocol"] = Value::String("openai_responses".to_owned());
        value["model_id"] = Value::String(Uuid::new_v4().to_string());
        value["provider_model_name"] = Value::String("model".to_owned());
        value["context_window"] = Value::from(128000);
        value["max_output_tokens"] = Value::from(4096);
        value["supports_tools"] = Value::Bool(true);
        value["supports_streaming"] = Value::Bool(true);
        value["supports_vision"] = Value::Bool(false);
        value["routing_tier"] = Value::from(2);
        value["quality_prior"] = Value::String("0.8500".to_owned());
        value["tool_reliability_prior"] = Value::String("0.9000".to_owned());
        value["latency_prior_ms"] = Value::from(100);
        value["model_family"] = Value::String("family".to_owned());
        value["model_vendor"] = Value::String("vendor".to_owned());
        value["architecture_class"] = Value::String("dense".to_owned());
        value["supports_reasoning"] = Value::Bool(true);
        value["reasoning_levels"] = serde_json::json!(["low", "medium"]);
        value["input_price_microusd_per_million"] = Value::from(1);
        value["output_price_microusd_per_million"] = Value::from(2);
        value["routing_enabled"] = Value::Bool(true);
        let json = serde_json::to_string(&Value::Array(vec![value])).unwrap();
        let parsed = parse_authorized_candidates(&json).unwrap();
        assert_eq!(parsed.len(), 1);
        assert_eq!(
            parsed[0].provider_protocol,
            Some(crate::rpc::reverse::ProviderProtocol::OpenaiResponses)
        );
        assert!(parsed[0].request_defaults_sha256.is_some());
    }

    #[test]
    fn legacy_fixed_candidate_without_v2_fields_is_accepted() {
        let mut value = candidate(Uuid::new_v4());
        value["request_defaults_sha256"] = Value::String(String::new());
        let object = value.as_object_mut().expect("candidate object");
        object.remove("request_defaults_sha256");
        let json = serde_json::to_string(&Value::Array(vec![value])).unwrap();
        let parsed = parse_authorized_candidates(&json).unwrap();
        assert_eq!(parsed.len(), 1);
        assert!(parsed[0].request_defaults_sha256.is_none());
        assert!(parsed[0].provider_protocol.is_none());
    }

    #[test]
    fn canonical_json_orders_keys_by_utf16_and_preserves_unicode() {
        let value = serde_json::json!({
            "\u{e000}": 2,
            "\u{10000}": 1,
            "metadata": {"中文": "\nquoted"},
        });
        let canonical = canonical_json(&value).unwrap();
        assert_eq!(
            canonical,
            "{\"metadata\":{\"中文\":\"\\nquoted\"},\"𐀀\":1,\"\":2}"
        );
    }

    #[tokio::test]
    async fn canonical_snapshot_rejects_whitespace_unknown_and_duplicate_candidates() {
        let store = SnapshotAuthorizationStore::default();
        let snapshot_id = Uuid::new_v4();
        let run_id = Uuid::new_v4();
        let raw = Value::Array(vec![candidate(Uuid::new_v4())]);
        let canonical = serde_json::to_string(&raw).unwrap();
        let hash = sha256_hex(canonical.as_bytes());
        assert!(store
            .register_snapshot(
                snapshot_id,
                run_id,
                canonical.clone(),
                hash,
                Utc::now() + chrono::Duration::minutes(5),
            )
            .await
            .is_ok());
        let noncanonical = format!(" {canonical} ");
        assert!(matches!(
            store
                .register_snapshot(
                    Uuid::new_v4(),
                    run_id,
                    noncanonical.clone(),
                    sha256_hex(noncanonical.as_bytes()),
                    Utc::now() + chrono::Duration::minutes(5),
                )
                .await,
            Err(AppError::Validation(code)) if code == "ROUTING_SNAPSHOT_INVALID"
        ));
        let mut unknown = candidate(Uuid::new_v4());
        unknown["unknown"] = Value::Bool(true);
        let unknown_raw = Value::Array(vec![unknown]);
        let unknown_json = serde_json::to_string(&unknown_raw).unwrap();
        assert!(store
            .register_snapshot(
                Uuid::new_v4(),
                run_id,
                unknown_json.clone(),
                sha256_hex(unknown_json.as_bytes()),
                Utc::now() + chrono::Duration::minutes(5),
            )
            .await
            .is_err());
        let duplicate_id = Uuid::new_v4();
        let duplicate_raw = Value::Array(vec![candidate(duplicate_id), candidate(duplicate_id)]);
        let duplicate_json = serde_json::to_string(&duplicate_raw).unwrap();
        assert!(store
            .register_snapshot(
                Uuid::new_v4(),
                run_id,
                duplicate_json.clone(),
                sha256_hex(duplicate_json.as_bytes()),
                Utc::now() + chrono::Duration::minutes(5),
            )
            .await
            .is_err());
    }

    #[tokio::test]
    async fn decision_rejects_duplicate_candidate_selection() {
        let store = SnapshotAuthorizationStore::default();
        let snapshot_id = Uuid::new_v4();
        let run_id = Uuid::new_v4();
        let id = Uuid::new_v4();
        let raw = Value::Array(vec![candidate(id)]);
        let json = serde_json::to_string(&raw).unwrap();
        store
            .register_snapshot(
                snapshot_id,
                run_id,
                json.clone(),
                sha256_hex(json.as_bytes()),
                Utc::now() + chrono::Duration::minutes(5),
            )
            .await
            .unwrap();
        assert!(store
            .register_decision(
                Uuid::new_v4(),
                run_id,
                snapshot_id,
                vec![
                    (id, SnapshotRouteRole::Single),
                    (id, SnapshotRouteRole::Single),
                ],
            )
            .await
            .is_err());
    }
}
