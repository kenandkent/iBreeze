use std::sync::Arc;
use std::time::Duration;

use chrono::{DateTime, Utc};
use serde_json::Value;
use tokio::sync::Mutex;
use tokio::time::{interval, timeout, Instant};
use uuid::Uuid;

use super::frame;
use super::multiplexer::{IpcError, Multiplexer};

pub const HEARTBEAT_INTERVAL: Duration = Duration::from_secs(5);
pub const HEARTBEAT_TIMEOUT: Duration = Duration::from_secs(3);
pub const MAX_MISSED_HEARTBEATS: u32 = 3;
pub const DEFAULT_RPC_TIMEOUT: Duration = Duration::from_secs(30);

#[derive(Debug, Clone)]
pub struct IpcSessionMeta {
    pub session_id: Uuid,
    pub trace_id: Uuid,
    pub generation: u64,
    pub connected_at: DateTime<Utc>,
}

#[derive(Clone)]
pub struct IpcSession {
    pub meta: IpcSessionMeta,
    pub multiplexer: Arc<Mutex<Multiplexer>>,
    cancel_token: tokio::sync::watch::Sender<bool>,
}

impl IpcSession {
    pub fn new(
        multiplexer: Arc<Mutex<Multiplexer>>,
        cancel_token: tokio::sync::watch::Sender<bool>,
    ) -> Self {
        let gen = multiplexer.blocking_lock().generation();
        Self {
            meta: IpcSessionMeta {
                session_id: Uuid::new_v4(),
                trace_id: Uuid::new_v4(),
                generation: gen,
                connected_at: Utc::now(),
            },
            multiplexer,
            cancel_token,
        }
    }

    pub fn is_cancelled(&self) -> bool {
        *self.cancel_token.borrow()
    }

    pub fn cancel(&self) {
        let _ = self.cancel_token.send(true);
    }

    pub async fn call(
        &self,
        method: &str,
        params: Value,
        deadline_at: Option<Instant>,
    ) -> Result<Value, IpcError> {
        let id = format!("core:{}", Uuid::new_v4());
        let deadline = deadline_at.unwrap_or_else(|| Instant::now() + DEFAULT_RPC_TIMEOUT);
        let mut mux = self.multiplexer.lock().await;
        let rx = mux.register_pending(id.clone(), deadline)?;

        let request = serde_json::json!({
            "jsonrpc": "2.0",
            "id": id,
            "method": method,
            "params": params,
            "meta": {
                "trace_id": self.meta.trace_id.to_string(),
                "ipc_session_id": self.meta.session_id.to_string(),
                "window_session_id": null,
                "idempotency_key": null,
                "deadline_at": (Utc::now() + chrono::Duration::from_std(SEND_TIMEOUT_SAFETY).unwrap()).to_rfc3339(),
            }
        });

        mux.send_json(&request).await?;
        drop(mux);

        let dur = deadline.saturating_duration_since(Instant::now());
        if dur.is_zero() {
            return Err(IpcError::DeadlineExceeded);
        }
        timeout(dur, rx)
            .await
            .ok()
            .and_then(|r| r.ok())
            .unwrap_or(Err(IpcError::DeadlineExceeded))
    }

    pub async fn notify(&self, method: &str, params: Value) -> Result<(), IpcError> {
        let notification = serde_json::json!({
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        });
        let mux = self.multiplexer.lock().await;
        mux.send_json(&notification).await
    }

    pub async fn respond(&self, id: &str, result: Result<Value, IpcError>) -> Result<(), IpcError> {
        let response = match result {
            Ok(value) => serde_json::json!({
                "jsonrpc": "2.0",
                "id": id,
                "result": value,
            }),
            Err(error) => serde_json::json!({
                "jsonrpc": "2.0",
                "id": id,
                "error": {
                    "code": -32000,
                    "message": error.to_string(),
                },
            }),
        };
        let mux = self.multiplexer.lock().await;
        mux.send_json(&response).await
    }

    pub async fn start_heartbeat(
        self: Arc<Self>,
        mut reader: impl tokio::io::AsyncRead + Unpin + Send + 'static,
    ) {
        let mut missed = 0u32;
        let mut ticker = interval(HEARTBEAT_INTERVAL);

        loop {
            tokio::select! {
                _ = ticker.tick() => {
                    if self.is_cancelled() {
                        break;
                    }
                    if let Err(e) = self.notify("system.heartbeat", serde_json::json!({})).await {
                        tracing::warn!(error = %e, "heartbeat send failed");
                        missed += 1;
                    } else {
                        missed = 0;
                    }
                    if missed >= MAX_MISSED_HEARTBEATS {
                        tracing::error!("heartbeat lost: connection considered dead");
                        break;
                    }
                }
                result = frame::read_frame(&mut reader) => {
                    match result {
                        Ok(value) => {
                            missed = 0;
                            if let Some(method) = value.get("method").and_then(|v| v.as_str()) {
                                if method == "system.heartbeat" {
                                    continue;
                                }
                            }
                        }
                        Err(_) => {
                            tracing::warn!("heartbeat reader error");
                            missed += 1;
                            if missed >= MAX_MISSED_HEARTBEATS {
                                break;
                            }
                        }
                    }
                }
            }
        }

        self.cancel();
        tracing::info!("heartbeat stopped, session cancelled");
    }
}

const SEND_TIMEOUT_SAFETY: Duration = Duration::from_secs(5);

#[cfg(test)]
mod tests {
    use super::*;
    use tokio::sync::mpsc;

    #[test]
    fn session_meta_has_unique_ids() {
        let (tx, _rx) = mpsc::unbounded_channel();
        let mux = Arc::new(Mutex::new(Multiplexer::new(tx)));
        let (cancel_tx, _) = tokio::sync::watch::channel(false);
        let s1 = IpcSession::new(mux.clone(), cancel_tx);
        let (cancel_tx2, _) = tokio::sync::watch::channel(false);
        let s2 = IpcSession::new(mux, cancel_tx2);
        assert_ne!(s1.meta.session_id, s2.meta.session_id);
        assert_ne!(s1.meta.trace_id, s2.meta.trace_id);
    }

    #[test]
    fn default_cancel_state_is_false() {
        let (tx, _rx) = mpsc::unbounded_channel();
        let mux = Arc::new(Mutex::new(Multiplexer::new(tx)));
        let (cancel_tx, _) = tokio::sync::watch::channel(false);
        let session = IpcSession::new(mux, cancel_tx);
        assert!(!session.is_cancelled());
    }

    #[test]
    fn cancel_sets_flag() {
        let (tx, _rx) = mpsc::unbounded_channel();
        let mux = Arc::new(Mutex::new(Multiplexer::new(tx)));
        let (cancel_tx, _) = tokio::sync::watch::channel(false);
        let session = IpcSession::new(mux, cancel_tx);
        session.cancel();
        assert!(session.is_cancelled());
    }
}
