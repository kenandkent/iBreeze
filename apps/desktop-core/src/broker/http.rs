use std::sync::Arc;
use std::time::Duration;

use reqwest::Client;
use serde_json::Value;
use tokio::sync::oneshot;
use tracing::{error, info};
use uuid::Uuid;

use crate::broker::credential::{CredentialAuthType, CredentialStore};
use crate::broker::dns_policy::DnsPolicy;
use crate::broker::http_stream::{BrokerEventKind, HttpStreamManager};
use crate::broker::lease::CredentialLeaseManager;
use crate::error::AppError;

pub const MAX_RETRIES: u32 = 3;
pub const MAX_STREAM_PAYLOAD_BYTES: usize = 16 * 1024 * 1024;

pub struct HttpBroker {
    client: Client,
    credential_store: Arc<CredentialStore>,
    dns_policy: Arc<DnsPolicy>,
    stream_manager: Arc<HttpStreamManager>,
    lease_manager: Arc<CredentialLeaseManager>,
}

impl HttpBroker {
    pub fn new(
        credential_store: Arc<CredentialStore>,
        dns_policy: Arc<DnsPolicy>,
        stream_manager: Arc<HttpStreamManager>,
        lease_manager: Arc<CredentialLeaseManager>,
    ) -> Self {
        let client = Client::builder()
            .timeout(Duration::from_secs(120))
            .connect_timeout(Duration::from_secs(10))
            .https_only(true)
            .redirect(reqwest::redirect::Policy::limited(5))
            .pool_max_idle_per_host(0)
            .build()
            .expect("Failed to build HTTP client");
        Self {
            client,
            credential_store,
            dns_policy,
            stream_manager,
            lease_manager,
        }
    }

    pub async fn start(
        &self,
        profile_directory_id: &str,
        provider_base_url: &str,
        credential_ref: Uuid,
        provider_release_id: Uuid,
        model_binding_id: Uuid,
        run_id: Uuid,
        relative_path: &str,
        request_body: Value,
        deadline_s: u64,
    ) -> Result<(Uuid, oneshot::Sender<()>), AppError> {
        let credential = self
            .credential_store
            .load_keychain_credential(profile_directory_id, credential_ref)?;

        let request_id = Uuid::new_v4();

        self.lease_manager
            .create_lease(
                credential_ref,
                request_id,
                run_id,
                provider_release_id,
                model_binding_id,
            )
            .await;

        let (cancel_tx, cancel_rx) = oneshot::channel::<()>();

        let target_url = format!(
            "{}{}",
            provider_base_url.trim_end_matches('/'),
            relative_path
        );

        let stream_manager = self.stream_manager.clone();
        let client = self.client.clone();
        let dns_policy = self.dns_policy.clone();

        tokio::spawn(async move {
            if let Err(e) = Self::execute_request(
                &client,
                &dns_policy,
                &stream_manager,
                &target_url,
                &credential,
                request_body,
                request_id,
                cancel_rx,
                deadline_s,
            )
            .await
            {
                error!(%request_id, error = %e, "credential.http.request failed");
                let _ = stream_manager.push_event(
                    request_id,
                    BrokerEventKind::Failed,
                    serde_json::json!({"error": e.to_string()}),
                );
                stream_manager.complete(request_id);
            }
        });

        Ok((request_id, cancel_tx))
    }

    async fn execute_request(
        client: &Client,
        dns_policy: &DnsPolicy,
        stream_manager: &HttpStreamManager,
        target_url: &str,
        credential: &crate::broker::credential::KeychainCredential,
        request_body: Value,
        request_id: Uuid,
        mut cancel_rx: oneshot::Receiver<()>,
        deadline_s: u64,
    ) -> Result<(), AppError> {
        dns_policy.validate_url(target_url)?;

        let host = url::Url::parse(target_url)
            .map_err(|e| AppError::Internal(format!("Invalid URL: {e}")))?
            .host_str()
            .ok_or_else(|| AppError::Security("URL has no host".to_owned()))?
            .to_owned();

        dns_policy.resolve_and_validate(&host).await?;

        let auth_value = match credential.auth_type {
            CredentialAuthType::Bearer => format!("Bearer {}", &*credential.secret),
            CredentialAuthType::XApiKey => credential.secret.to_string(),
        };

        let auth_header = match credential.auth_type {
            CredentialAuthType::Bearer => "Authorization",
            CredentialAuthType::XApiKey => "X-Api-Key",
        };

        let builder = client
            .post(target_url)
            .header(auth_header, auth_value)
            .header("Content-Type", "application/json")
            .json(&request_body);

        let deadline = tokio::time::Instant::now() + Duration::from_secs(deadline_s);
        let mut last_error = None;

        for attempt in 0..=MAX_RETRIES {
            if tokio::time::Instant::now() >= deadline {
                return Err(AppError::Network("Deadline exceeded".to_owned()));
            }

            if cancel_rx.try_recv().is_ok() {
                info!(%request_id, "request cancelled");
                return Ok(());
            }

            if attempt > 0 {
                let delay = match attempt {
                    1 => Duration::from_secs(1),
                    2 => Duration::from_secs(2),
                    _ => Duration::from_secs(4),
                };
                tokio::time::sleep(delay).await;
            }

            let req = match builder.try_clone() {
                Some(b) => b.build().map_err(|e| AppError::Internal(e.to_string()))?,
                None => return Err(AppError::Internal("Request body not cloneable".to_owned())),
            };

            match client.execute(req).await {
                Ok(resp) => {
                    let status = resp.status();
                    if status.is_success() {
                        return Self::consume_response(stream_manager, resp, request_id).await;
                    }
                    match status.as_u16() {
                        401 | 403 => {
                            return Err(AppError::Unauthorized("CREDENTIAL_UNAVAILABLE".to_owned()))
                        }
                        400 | 404 => {
                            return Err(AppError::Validation(
                                "PROVIDER_CONFIGURATION_INVALID".to_owned(),
                            ))
                        }
                        408 | 429 | 500..=599 => {
                            last_error = Some(AppError::Network(format!("HTTP {status}")));
                            continue;
                        }
                        s => return Err(AppError::Network(format!("Unexpected status {s}"))),
                    }
                }
                Err(e) if e.is_timeout() || e.is_connect() || e.is_request() => {
                    last_error = Some(AppError::Network(e.to_string()));
                    if attempt < MAX_RETRIES {
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
    ) -> Result<(), AppError> {
        let is_streaming = response
            .headers()
            .get(reqwest::header::TRANSFER_ENCODING)
            .and_then(|v| v.to_str().ok())
            .map_or(false, |v| v.contains("chunked"))
            || response
                .headers()
                .get(reqwest::header::CONTENT_TYPE)
                .and_then(|v| v.to_str().ok())
                .map_or(false, |v| {
                    v.contains("text/event-stream") || v.contains("text/plain")
                });

        if is_streaming {
            let mut stream = response.bytes_stream();
            use futures_util::StreamExt;
            while let Some(chunk) = stream.next().await {
                match chunk {
                    Ok(bytes) => {
                        let text = String::from_utf8_lossy(&bytes);
                        for line in text.lines() {
                            if let Some(data) = line.strip_prefix("data: ") {
                                if data == "[DONE]" {
                                    continue;
                                }
                                if let Ok(value) = serde_json::from_str::<Value>(data) {
                                    let kind = detect_event_kind(&value);
                                    stream_manager.push_event(request_id, kind, value);
                                }
                            }
                        }
                    }
                    Err(e) => return Err(AppError::Network(format!("Stream error: {e}"))),
                }
            }
        } else {
            let body = response
                .bytes()
                .await
                .map_err(|e| AppError::Network(e.to_string()))?;
            if body.len() > MAX_STREAM_PAYLOAD_BYTES {
                return Err(AppError::Network("Response too large".to_owned()));
            }
            match serde_json::from_slice::<Value>(&body) {
                Ok(value) => {
                    stream_manager.push_event(request_id, BrokerEventKind::Completed, value);
                }
                Err(_) => {
                    let text = String::from_utf8_lossy(&body);
                    stream_manager.push_event(
                        request_id,
                        BrokerEventKind::OutputTextDelta,
                        serde_json::json!({"text": text}),
                    );
                    stream_manager.push_event(
                        request_id,
                        BrokerEventKind::Completed,
                        serde_json::json!({"status": "completed"}),
                    );
                }
            }
        }

        stream_manager.complete(request_id);
        Ok(())
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
}
