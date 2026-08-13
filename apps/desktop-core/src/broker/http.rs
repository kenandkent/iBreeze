use std::collections::BTreeSet;
use std::sync::Arc;
use std::time::Duration;

use rand::Rng;
use reqwest::Client;
use serde_json::Value;
use tokio::sync::{mpsc, oneshot};
use tokio::time::timeout;
use tracing::{error, info};
use uuid::Uuid;

use crate::broker::credential::{CredentialAuthType, CredentialStore};
use crate::broker::dns_policy::DnsPolicy;
use crate::broker::domain_policy::NormalizedDomain;
use crate::broker::egress::EgressBroker;
use crate::broker::http_stream::{BrokerEvent, BrokerEventKind, HttpStreamManager};
use crate::broker::lease::CredentialLeaseManager;
use crate::error::AppError;

pub const MAX_RETRIES: u32 = 3;
pub const MAX_STREAM_PAYLOAD_BYTES: usize = 16 * 1024 * 1024;
const MAX_RETRY_AFTER_SECONDS: u64 = 900;

#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum ProviderFailureKind {
    RateLimited,
    ProviderOverloaded,
    TransportTransient,
    Timeout,
    ContextOverflow,
    AuthInvalid,
    ModelNotFound,
    UnsupportedCapability,
    InsufficientCredits,
    BadRequest,
    PolicyRefusal,
    InvalidResponse,
}

pub struct HttpBroker {
    credential_store: Arc<CredentialStore>,
    dns_policy: Arc<DnsPolicy>,
    stream_manager: Arc<HttpStreamManager>,
    lease_manager: Arc<CredentialLeaseManager>,
    egress_broker: Arc<EgressBroker>,
}

impl HttpBroker {
    pub fn new(
        credential_store: Arc<CredentialStore>,
        dns_policy: Arc<DnsPolicy>,
        stream_manager: Arc<HttpStreamManager>,
        lease_manager: Arc<CredentialLeaseManager>,
        egress_broker: Arc<EgressBroker>,
    ) -> Self {
        Self {
            credential_store,
            dns_policy,
            stream_manager,
            lease_manager,
            egress_broker,
        }
    }

    #[allow(clippy::too_many_arguments)]
    pub async fn start(
        &self,
        profile_directory_id: &str,
        provider_base_url: &str,
        provider_auth_scheme: &str,
        credential_ref: Uuid,
        provider_release_id: Uuid,
        model_binding_id: Uuid,
        run_id: Uuid,
        relative_path: &str,
        request_body: Value,
        deadline_s: u64,
        max_retries: u32,
    ) -> Result<(Uuid, oneshot::Sender<()>, mpsc::Receiver<BrokerEvent>), AppError> {
        let credential = self
            .credential_store
            .load_keychain_credential(profile_directory_id, credential_ref)?;
        let auth_scheme_matches = match provider_auth_scheme {
            "bearer" => credential.auth_type == CredentialAuthType::Bearer,
            "x-api-key" => credential.auth_type == CredentialAuthType::XApiKey,
            _ => false,
        };
        if !auth_scheme_matches {
            return Err(AppError::Validation(
                "CREDENTIAL_AUTH_SCHEME_MISMATCH".to_owned(),
            ));
        }

        let request_id = Uuid::new_v4();
        let provider_url = url::Url::parse(provider_base_url)
            .map_err(|_| AppError::Validation("PROVIDER_URL_INVALID".to_owned()))?;
        let provider_host = provider_url
            .host_str()
            .ok_or_else(|| AppError::Validation("PROVIDER_URL_HOST_REQUIRED".to_owned()))?;
        let mut allowed_domains = BTreeSet::new();
        allowed_domains.insert(NormalizedDomain::new(provider_host));
        let egress_lease = self
            .egress_broker
            .create_lease(run_id, allowed_domains)
            .await?;
        let proxy_url = egress_lease.proxy_url().to_string();

        let credential_lease = self
            .lease_manager
            .create_lease(
                credential_ref,
                request_id,
                run_id,
                provider_release_id,
                model_binding_id,
            )
            .await;

        let (cancel_tx, cancel_rx) = oneshot::channel::<()>();
        self.stream_manager.create_stream(request_id).await;
        // Subscribe before spawning the provider task.  This removes the
        // startup race in which a fast provider could fill the replay history
        // before the reverse-RPC event consumer was attached.
        let receiver = self.stream_manager.subscribe(request_id).await?;

        let target_url = format!(
            "{}{}",
            provider_base_url.trim_end_matches('/'),
            relative_path
        );

        let stream_manager = self.stream_manager.clone();
        let dns_policy = self.dns_policy.clone();
        let egress_broker = self.egress_broker.clone();
        let egress_lease_id = egress_lease.lease_id;
        let lease_manager = self.lease_manager.clone();
        let credential_lease_id = credential_lease.lease_id;

        tokio::spawn(async move {
            if let Err(e) = Self::execute_request(
                &dns_policy,
                &stream_manager,
                &target_url,
                &credential,
                request_body,
                request_id,
                cancel_rx,
                deadline_s,
                &proxy_url,
                max_retries,
            )
            .await
            {
                error!(%request_id, error = %e, "credential.http.request failed");
                let _ = stream_manager
                    .push_event_async(
                        request_id,
                        BrokerEventKind::Failed,
                        sanitized_failure_payload(&e, request_id),
                    )
                    .await;
                stream_manager.complete_async(request_id).await;
            }
            let _ = egress_broker.revoke_lease_by_id(egress_lease_id).await;
            let _ = lease_manager.revoke_lease(credential_lease_id).await;
        });

        Ok((request_id, cancel_tx, receiver))
    }

    pub async fn active_credential_leases(&self, credential_ref: Uuid) -> usize {
        self.lease_manager
            .active_for_credential(credential_ref)
            .await
    }

    pub async fn subscribe(
        &self,
        request_id: Uuid,
    ) -> Result<mpsc::Receiver<BrokerEvent>, AppError> {
        self.stream_manager.subscribe(request_id).await
    }

    pub async fn wait_for_result(
        &self,
        request_id: Uuid,
        deadline_s: u64,
    ) -> Result<Value, AppError> {
        let receiver = self.stream_manager.subscribe(request_id).await?;
        self.wait_for_receiver(request_id, receiver, deadline_s)
            .await
    }

    pub(crate) async fn wait_for_receiver(
        &self,
        request_id: Uuid,
        mut receiver: mpsc::Receiver<BrokerEvent>,
        deadline_s: u64,
    ) -> Result<Value, AppError> {
        let read_events = async {
            let mut events = Vec::new();
            while let Some(event) = receiver.recv().await {
                match event.event {
                    BrokerEventKind::Failed => {
                        return Err(AppError::Network(event.payload.to_string()))
                    }
                    BrokerEventKind::Completed => return Ok(event.payload),
                    _ => events.push(event.payload),
                }
            }
            if events.is_empty() {
                Err(AppError::Network("PROVIDER_EMPTY_RESPONSE".to_owned()))
            } else {
                Ok(serde_json::json!({"events": events}))
            }
        };
        let timed = timeout(Duration::from_secs(deadline_s.max(1)), read_events).await;
        self.stream_manager.drop_stream(request_id).await;
        let result =
            timed.map_err(|_| AppError::Network("PROVIDER_DEADLINE_EXCEEDED".to_owned()))??;
        Ok(result)
    }

    #[allow(clippy::too_many_arguments)]
    async fn execute_request(
        dns_policy: &DnsPolicy,
        stream_manager: &HttpStreamManager,
        target_url: &str,
        credential: &crate::broker::credential::KeychainCredential,
        request_body: Value,
        request_id: Uuid,
        mut cancel_rx: oneshot::Receiver<()>,
        deadline_s: u64,
        proxy_url: &str,
        max_retries: u32,
    ) -> Result<(), AppError> {
        dns_policy.validate_url(target_url)?;

        let host = url::Url::parse(target_url)
            .map_err(|e| AppError::Internal(format!("Invalid URL: {e}")))?
            .host_str()
            .ok_or_else(|| AppError::Security("URL has no host".to_owned()))?
            .to_owned();

        dns_policy.resolve_and_validate(&host).await?;

        let auth_value = match credential.auth_type {
            CredentialAuthType::Bearer => format!("Bearer {}", *credential.secret),
            CredentialAuthType::XApiKey => credential.secret.to_string(),
        };

        let auth_header = match credential.auth_type {
            CredentialAuthType::Bearer => "Authorization",
            CredentialAuthType::XApiKey => "X-Api-Key",
        };

        let proxy = reqwest::Proxy::all(proxy_url)
            .map_err(|error| AppError::Internal(format!("Invalid egress proxy: {error}")))?;
        let broker_client = Client::builder()
            .timeout(Duration::from_secs(120))
            .connect_timeout(Duration::from_secs(10))
            .https_only(true)
            .redirect(reqwest::redirect::Policy::none())
            .proxy(proxy)
            .build()
            .map_err(|error| AppError::Internal(format!("Build egress client: {error}")))?;
        let builder = broker_client
            .post(target_url)
            .header(auth_header, auth_value)
            .header("Content-Type", "application/json")
            .json(&request_body);

        let deadline = tokio::time::Instant::now() + Duration::from_secs(deadline_s);
        let mut last_error = None;
        let mut retry_after = None;

        for attempt in 0..=max_retries {
            if tokio::time::Instant::now() >= deadline {
                return Err(AppError::Network("Deadline exceeded".to_owned()));
            }

            if cancel_rx.try_recv().is_ok() {
                info!(%request_id, "request cancelled");
                let _ = stream_manager
                    .push_event_async(
                        request_id,
                        BrokerEventKind::Completed,
                        serde_json::json!({"state": "cancelled"}),
                    )
                    .await;
                stream_manager.complete_async(request_id).await;
                return Ok(());
            }

            if attempt > 0 {
                let base_delay = retry_after.take().unwrap_or(match attempt {
                    1 => Duration::from_secs(1),
                    2 => Duration::from_secs(2),
                    _ => Duration::from_secs(4),
                });
                let jitter_ms = rand::thread_rng().gen_range(0..=250_u64);
                let delay = base_delay.saturating_add(Duration::from_millis(jitter_ms));
                let remaining = deadline.saturating_duration_since(tokio::time::Instant::now());
                if delay >= remaining {
                    return Err(last_error.unwrap_or_else(|| {
                        AppError::Network("PROVIDER_DEADLINE_EXCEEDED".to_owned())
                    }));
                }
                tokio::select! {
                    _ = &mut cancel_rx => {
                        let _ = stream_manager
                            .push_event_async(
                                request_id,
                                BrokerEventKind::Completed,
                                serde_json::json!({"state": "cancelled"}),
                            )
                            .await;
                        stream_manager.complete_async(request_id).await;
                        return Ok(());
                    }
                    _ = tokio::time::sleep(delay) => {}
                }
            }

            let req = match builder.try_clone() {
                Some(b) => b.build().map_err(|e| AppError::Internal(e.to_string()))?,
                None => return Err(AppError::Internal("Request body not cloneable".to_owned())),
            };

            let remaining = deadline.saturating_duration_since(tokio::time::Instant::now());
            let execute_result = tokio::select! {
                _ = &mut cancel_rx => {
                    info!(%request_id, "request cancelled while connecting");
                    let _ = stream_manager
                        .push_event_async(
                            request_id,
                            BrokerEventKind::Completed,
                            serde_json::json!({"state": "cancelled"}),
                        )
                        .await;
                    stream_manager.complete_async(request_id).await;
                    return Ok(());
                }
                result = tokio::time::timeout(remaining, broker_client.execute(req)) => {
                    match result {
                        Ok(result) => result,
                        Err(_) => return Err(AppError::Network("Deadline exceeded".to_owned())),
                    }
                }
            };

            match execute_result {
                Ok(resp) => {
                    let status = resp.status();
                    let response_retry_after = retry_after_from_response(&resp);
                    if status.is_success() {
                        return Self::consume_response(
                            stream_manager,
                            resp,
                            request_id,
                            &mut cancel_rx,
                        )
                        .await;
                    }
                    let error_body = resp
                        .bytes()
                        .await
                        .map(|body| body.into_iter().take(64 * 1024).collect::<Vec<_>>())
                        .unwrap_or_default();
                    let failure_kind = failure_kind_for_response(status, &error_body);
                    match failure_kind {
                        ProviderFailureKind::Timeout
                        | ProviderFailureKind::RateLimited
                        | ProviderFailureKind::ProviderOverloaded => {
                            let retry_ms = response_retry_after
                                .map(|value| value.as_millis().min(u64::MAX as u128) as u64)
                                .unwrap_or(0);
                            last_error = Some(AppError::Network(format!(
                                "{}:HTTP {status}:retry_after_ms={retry_ms}",
                                failure_kind.as_str()
                            )));
                            retry_after = response_retry_after;
                            continue;
                        }
                        ProviderFailureKind::AuthInvalid => {
                            return Err(AppError::Unauthorized("AUTH_INVALID".to_owned()))
                        }
                        ProviderFailureKind::ModelNotFound
                        | ProviderFailureKind::ContextOverflow
                        | ProviderFailureKind::UnsupportedCapability
                        | ProviderFailureKind::InsufficientCredits
                        | ProviderFailureKind::BadRequest
                        | ProviderFailureKind::PolicyRefusal => {
                            return Err(AppError::Validation(failure_kind.as_str().to_owned()))
                        }
                        ProviderFailureKind::TransportTransient
                        | ProviderFailureKind::InvalidResponse => {
                            return Err(AppError::Network(failure_kind.as_str().to_owned()))
                        }
                    }
                }
                Err(e) if e.is_timeout() || e.is_connect() || e.is_request() => {
                    last_error = Some(AppError::Network(format!("TRANSPORT_TRANSIENT:{}", e)));
                    if attempt < max_retries {
                        continue;
                    }
                    break;
                }
                Err(e) => return Err(AppError::Network(e.to_string())),
            }
        }

        Err(last_error.unwrap_or_else(|| AppError::Network("Request failed".to_owned())))
    }

    async fn consume_response(
        stream_manager: &HttpStreamManager,
        response: reqwest::Response,
        request_id: Uuid,
        cancel_rx: &mut oneshot::Receiver<()>,
    ) -> Result<(), AppError> {
        let is_streaming = response
            .headers()
            .get(reqwest::header::TRANSFER_ENCODING)
            .and_then(|v| v.to_str().ok())
            .is_some_and(|v| v.contains("chunked"))
            || response
                .headers()
                .get(reqwest::header::CONTENT_TYPE)
                .and_then(|v| v.to_str().ok())
                .is_some_and(|v| v.contains("text/event-stream") || v.contains("text/plain"));

        if is_streaming {
            let mut stream = response.bytes_stream();
            use futures_util::StreamExt;
            let mut buffered: Vec<u8> = Vec::new();
            let mut total_bytes = 0usize;
            loop {
                let chunk = tokio::select! {
                    _ = &mut *cancel_rx => {
                        let _ = stream_manager
                            .push_event_async(
                                request_id,
                                BrokerEventKind::Completed,
                                serde_json::json!({"state": "cancelled"}),
                            )
                            .await;
                        stream_manager.complete_async(request_id).await;
                        return Ok(());
                    }
                    chunk = stream.next() => chunk,
                };
                let Some(chunk) = chunk else { break };
                match chunk {
                    Ok(bytes) => {
                        total_bytes = total_bytes.saturating_add(bytes.len());
                        if total_bytes > MAX_STREAM_PAYLOAD_BYTES {
                            return Err(AppError::Network("Response too large".to_owned()));
                        }
                        buffered.extend_from_slice(&bytes);
                        while let Some(newline) = buffered.iter().position(|byte| *byte == b'\n') {
                            let mut line = buffered.drain(..=newline).collect::<Vec<_>>();
                            line.pop();
                            if line.last() == Some(&b'\r') {
                                line.pop();
                            }
                            push_sse_line(stream_manager, request_id, &line).await?;
                        }
                    }
                    Err(e) => return Err(AppError::Network(format!("Stream error: {e}"))),
                }
            }
            if !buffered.is_empty() {
                if buffered.last() == Some(&b'\r') {
                    buffered.pop();
                }
                push_sse_line(stream_manager, request_id, &buffered).await?;
            }
            stream_manager
                .push_event_async(
                    request_id,
                    BrokerEventKind::Completed,
                    serde_json::json!({"status": "completed"}),
                )
                .await?;
        } else {
            let body = tokio::select! {
                _ = &mut *cancel_rx => {
                    let _ = stream_manager
                        .push_event_async(
                            request_id,
                            BrokerEventKind::Completed,
                            serde_json::json!({"state": "cancelled"}),
                        )
                        .await;
                    stream_manager.complete_async(request_id).await;
                    return Ok(());
                }
                result = response.bytes() => result.map_err(|e| AppError::Network(e.to_string()))?,
            };
            if body.len() > MAX_STREAM_PAYLOAD_BYTES {
                return Err(AppError::Network("Response too large".to_owned()));
            }
            match serde_json::from_slice::<Value>(&body) {
                Ok(value) if detect_event_kind(&value) == BrokerEventKind::Failed => {
                    stream_manager
                        .push_event_async(
                            request_id,
                            BrokerEventKind::Failed,
                            serde_json::json!({"error_code": "PROVIDER_ERROR"}),
                        )
                        .await?;
                }
                Ok(value) => {
                    stream_manager
                        .push_event_async(request_id, BrokerEventKind::Completed, value)
                        .await?;
                }
                Err(_) => {
                    let text = String::from_utf8_lossy(&body);
                    stream_manager
                        .push_event_async(
                            request_id,
                            BrokerEventKind::OutputTextDelta,
                            serde_json::json!({"text": text}),
                        )
                        .await?;
                    stream_manager
                        .push_event_async(
                            request_id,
                            BrokerEventKind::Completed,
                            serde_json::json!({"status": "completed"}),
                        )
                        .await?;
                }
            }
        }

        stream_manager.complete_async(request_id).await;
        Ok(())
    }
}

async fn push_sse_line(
    stream_manager: &HttpStreamManager,
    request_id: Uuid,
    line: &[u8],
) -> Result<(), AppError> {
    let line = std::str::from_utf8(line)
        .map_err(|_| AppError::Network("PROVIDER_RESPONSE_INVALID_UTF8".to_owned()))?;
    let Some(data) = line.strip_prefix("data: ") else {
        return Ok(());
    };
    if data == "[DONE]" {
        return Ok(());
    }
    let Ok(value) = serde_json::from_str::<Value>(data) else {
        return Ok(());
    };
    let kind = detect_event_kind(&value);
    let payload = if kind == BrokerEventKind::Failed {
        serde_json::json!({"error_code": "PROVIDER_ERROR"})
    } else {
        value
    };
    stream_manager
        .push_event_async(request_id, kind, payload)
        .await
}

fn retry_after_from_response(response: &reqwest::Response) -> Option<Duration> {
    let value = response
        .headers()
        .get(reqwest::header::RETRY_AFTER)
        .and_then(|value| value.to_str().ok())?;
    if let Ok(seconds) = value.trim().parse::<u64>() {
        return Some(Duration::from_secs(seconds.min(MAX_RETRY_AFTER_SECONDS)));
    }
    let date = chrono::DateTime::parse_from_rfc2822(value)
        .ok()?
        .with_timezone(&chrono::Utc);
    let seconds = (date - chrono::Utc::now()).num_seconds().max(0) as u64;
    Some(Duration::from_secs(seconds.min(MAX_RETRY_AFTER_SECONDS)))
}

fn sanitized_failure_payload(error: &AppError, request_id: Uuid) -> Value {
    let (error_code, kind) = match error {
        AppError::Unauthorized(message) => ("AUTH_INVALID", message.as_str()),
        AppError::Validation(message) => ("BAD_REQUEST", message.as_str()),
        AppError::Network(message) => ("PROVIDER_NETWORK_ERROR", message.as_str()),
        AppError::Cancelled(_) => ("PROVIDER_CANCELLED", "TRANSPORT_TRANSIENT"),
        _ => ("PROVIDER_REQUEST_FAILED", "INVALID_RESPONSE"),
    };
    let failure_kind = if kind.contains("Deadline exceeded") {
        "TIMEOUT"
    } else {
        kind.split(':').next().unwrap_or("INVALID_RESPONSE")
    };
    let http_status = kind
        .split("HTTP ")
        .nth(1)
        .and_then(|value| value.split(':').next())
        .and_then(|value| value.parse::<u16>().ok());
    let retry_after_ms = kind
        .split("retry_after_ms=")
        .nth(1)
        .and_then(|value| value.split(':').next())
        .and_then(|value| value.parse::<u64>().ok());
    serde_json::json!({
        "request_id": request_id,
        "error_code": error_code,
        "failure_kind": failure_kind,
        "http_status": http_status,
        "retry_after_ms": retry_after_ms,
        "safe_message": error_code,
        "visible_content": false
    })
}

fn failure_kind_for_response(status: reqwest::StatusCode, body: &[u8]) -> ProviderFailureKind {
    let body_text = String::from_utf8_lossy(body).to_ascii_lowercase();
    let contains = |needles: &[&str]| needles.iter().any(|needle| body_text.contains(needle));
    if contains(&[
        "context_length",
        "context_window",
        "too_many_tokens",
        "max_tokens_exceeded",
    ]) {
        return ProviderFailureKind::ContextOverflow;
    }
    if contains(&[
        "insufficient_quota",
        "insufficient_credits",
        "billing",
        "credit_balance",
    ]) {
        return ProviderFailureKind::InsufficientCredits;
    }
    if contains(&[
        "content_filter",
        "safety",
        "policy_refusal",
        "policy violation",
        "refusal",
        "refused",
    ]) {
        return ProviderFailureKind::PolicyRefusal;
    }
    if contains(&[
        "unsupported",
        "not_supported",
        "capability_not_available",
        "tool_choice",
    ]) {
        return ProviderFailureKind::UnsupportedCapability;
    }
    failure_kind_for_status(status)
}

fn failure_kind_for_status(status: reqwest::StatusCode) -> ProviderFailureKind {
    match status.as_u16() {
        408 => ProviderFailureKind::Timeout,
        429 => ProviderFailureKind::RateLimited,
        500..=599 => ProviderFailureKind::ProviderOverloaded,
        404 => ProviderFailureKind::ModelNotFound,
        401 | 403 => ProviderFailureKind::AuthInvalid,
        413 => ProviderFailureKind::ContextOverflow,
        402 => ProviderFailureKind::InsufficientCredits,
        422 => ProviderFailureKind::UnsupportedCapability,
        _ => ProviderFailureKind::BadRequest,
    }
}

impl ProviderFailureKind {
    fn as_str(self) -> &'static str {
        match self {
            Self::RateLimited => "RATE_LIMITED",
            Self::ProviderOverloaded => "PROVIDER_OVERLOADED",
            Self::TransportTransient => "TRANSPORT_TRANSIENT",
            Self::Timeout => "TIMEOUT",
            Self::ContextOverflow => "CONTEXT_OVERFLOW",
            Self::AuthInvalid => "AUTH_INVALID",
            Self::ModelNotFound => "MODEL_NOT_FOUND",
            Self::UnsupportedCapability => "UNSUPPORTED_CAPABILITY",
            Self::InsufficientCredits => "INSUFFICIENT_CREDITS",
            Self::BadRequest => "BAD_REQUEST",
            Self::PolicyRefusal => "POLICY_REFUSAL",
            Self::InvalidResponse => "INVALID_RESPONSE",
        }
    }
}

pub fn detect_event_kind(value: &Value) -> BrokerEventKind {
    if value.get("type").and_then(|v| v.as_str()) == Some("text_delta")
        || value.get("delta").is_some()
    {
        BrokerEventKind::OutputTextDelta
    } else if value.get("tool_call").is_some()
        || value.get("type").and_then(|v| v.as_str()) == Some("tool_use")
    {
        BrokerEventKind::ToolCallDelta
    } else if value.get("usage").is_some() || value.get("input_tokens").is_some() {
        BrokerEventKind::Usage
    } else if value.get("type").and_then(|v| v.as_str()) == Some("completed")
        || value.get("stop_reason").is_some()
        || value.get("stop_sequence").is_some()
    {
        BrokerEventKind::Completed
    } else if value.get("type").and_then(|v| v.as_str()) == Some("error")
        || value.get("error").is_some()
    {
        BrokerEventKind::Failed
    } else {
        BrokerEventKind::OutputTextDelta
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::broker::http_stream::BrokerEventKind;

    #[test]
    fn detect_kind_text() {
        let v = serde_json::json!({"type": "text_delta", "text": "H"});
        assert_eq!(detect_event_kind(&v), BrokerEventKind::OutputTextDelta);
    }

    #[test]
    fn detect_kind_tool() {
        let v = serde_json::json!({"tool_call": {"name": "r"}});
        assert_eq!(detect_event_kind(&v), BrokerEventKind::ToolCallDelta);
    }

    #[test]
    fn detect_kind_usage() {
        let v = serde_json::json!({"usage": {"in": 1}});
        assert_eq!(detect_event_kind(&v), BrokerEventKind::Usage);
    }

    #[test]
    fn detect_kind_completed() {
        let v = serde_json::json!({"stop_reason": "end_turn"});
        assert_eq!(detect_event_kind(&v), BrokerEventKind::Completed);
    }

    #[test]
    fn detect_kind_error() {
        let v = serde_json::json!({"error": {"msg": "fail"}});
        assert_eq!(detect_event_kind(&v), BrokerEventKind::Failed);
    }

    #[test]
    fn detect_kind_delta() {
        let v = serde_json::json!({"delta": {"text": "x"}});
        assert_eq!(detect_event_kind(&v), BrokerEventKind::OutputTextDelta);
    }

    #[test]
    fn detect_kind_tool_use() {
        let v = serde_json::json!({"type": "tool_use", "name": "x"});
        assert_eq!(detect_event_kind(&v), BrokerEventKind::ToolCallDelta);
    }

    #[test]
    fn classify_provider_failure_statuses() {
        use reqwest::StatusCode;

        let cases = [
            (StatusCode::REQUEST_TIMEOUT, ProviderFailureKind::Timeout),
            (
                StatusCode::TOO_MANY_REQUESTS,
                ProviderFailureKind::RateLimited,
            ),
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                ProviderFailureKind::ProviderOverloaded,
            ),
            (StatusCode::NOT_FOUND, ProviderFailureKind::ModelNotFound),
            (StatusCode::UNAUTHORIZED, ProviderFailureKind::AuthInvalid),
            (
                StatusCode::PAYLOAD_TOO_LARGE,
                ProviderFailureKind::ContextOverflow,
            ),
            (
                StatusCode::PAYMENT_REQUIRED,
                ProviderFailureKind::InsufficientCredits,
            ),
            (
                StatusCode::UNPROCESSABLE_ENTITY,
                ProviderFailureKind::UnsupportedCapability,
            ),
            (StatusCode::BAD_REQUEST, ProviderFailureKind::BadRequest),
        ];

        for (status, expected) in cases {
            assert_eq!(failure_kind_for_response(status, b""), expected);
        }
    }

    #[test]
    fn classify_structured_provider_failure_bodies() {
        use reqwest::StatusCode;

        assert_eq!(
            failure_kind_for_response(
                StatusCode::BAD_REQUEST,
                br#"{"error":"context_length_exceeded"}"#
            ),
            ProviderFailureKind::ContextOverflow
        );
        assert_eq!(
            failure_kind_for_response(StatusCode::BAD_REQUEST, br#"{"code":"insufficient_quota"}"#),
            ProviderFailureKind::InsufficientCredits
        );
        assert_eq!(
            failure_kind_for_response(
                StatusCode::BAD_REQUEST,
                br#"{"error":{"type":"content_filter"}}"#
            ),
            ProviderFailureKind::PolicyRefusal
        );
        assert_eq!(
            failure_kind_for_response(
                StatusCode::BAD_REQUEST,
                br#"{"message":"tool_choice is not supported"}"#
            ),
            ProviderFailureKind::UnsupportedCapability
        );
    }

    #[test]
    fn classify_failure_body_case_insensitively_without_leaking_body() {
        use reqwest::StatusCode;

        assert_eq!(
            failure_kind_for_response(StatusCode::BAD_REQUEST, b"CONTEXT_WINDOW exceeded"),
            ProviderFailureKind::ContextOverflow
        );
        assert_eq!(
            failure_kind_for_response(StatusCode::BAD_REQUEST, b"provider refused this request"),
            ProviderFailureKind::PolicyRefusal
        );
        assert_eq!(
            failure_kind_for_response(StatusCode::BAD_REQUEST, b"opaque provider failure"),
            ProviderFailureKind::BadRequest
        );
    }
}
