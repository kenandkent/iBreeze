use std::collections::BTreeSet;
use std::sync::Arc;
use std::time::Instant;

use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use rand::RngCore;
use tokio::net::TcpListener;
use tokio::sync::{oneshot, Mutex, RwLock};
use tracing::info;
use uuid::Uuid;
use zeroize::Zeroizing;

use crate::broker::domain_policy::NormalizedDomain;
use crate::error::AppError;

pub struct EgressLease {
    pub lease_id: Uuid,
    pub run_id: Uuid,
    pub listener: Option<TcpListener>,
    pub port: u16,
    pub token: Zeroizing<[u8; 32]>,
    pub token_b64: Zeroizing<String>,
    pub allowed_domains: BTreeSet<NormalizedDomain>,
    pub created_at: Instant,
    pub cancel: Mutex<Option<oneshot::Sender<()>>>,
}

impl EgressLease {
    pub fn proxy_url(&self) -> Zeroizing<String> {
        Zeroizing::new(format!(
            "http://ibreeze:{}@127.0.0.1:{}",
            &*self.token_b64, self.port
        ))
    }
}

pub struct EgressBroker {
    leases: RwLock<Vec<Arc<EgressLease>>>,
}

impl EgressBroker {
    pub fn new() -> Self {
        Self {
            leases: RwLock::new(Vec::new()),
        }
    }

    pub async fn create_lease(
        &self,
        run_id: Uuid,
        allowed_domains: BTreeSet<NormalizedDomain>,
    ) -> Result<Arc<EgressLease>, AppError> {
        let listener = TcpListener::bind("127.0.0.1:0")
            .await
            .map_err(|e| AppError::Internal(format!("Failed to bind egress proxy: {e}")))?;

        let port = listener
            .local_addr()
            .map_err(|e| AppError::Internal(format!("Failed to get egress port: {e}")))?
            .port();

        let mut token_bytes = Zeroizing::new([0u8; 32]);
        rand::thread_rng().fill_bytes(&mut *token_bytes);
        let token_b64 = Zeroizing::new(URL_SAFE_NO_PAD.encode(&*token_bytes));

        let (cancel_tx, _) = oneshot::channel::<()>();

        let lease = Arc::new(EgressLease {
            lease_id: Uuid::new_v4(),
            run_id,
            listener: Some(listener),
            port,
            token: token_bytes,
            token_b64,
            allowed_domains,
            created_at: Instant::now(),
            cancel: Mutex::new(Some(cancel_tx)),
        });

        self.leases.write().await.push(lease.clone());
        info!(%run_id, port, "egress lease created");

        Ok(lease)
    }

    pub async fn get_lease(&self, run_id: Uuid) -> Option<Arc<EgressLease>> {
        let leases = self.leases.read().await;
        leases.iter().find(|l| l.run_id == run_id).cloned()
    }

    pub async fn get_lease_by_port(&self, port: u16) -> Option<Arc<EgressLease>> {
        let leases = self.leases.read().await;
        leases.iter().find(|l| l.port == port).cloned()
    }

    pub async fn revoke_lease(&self, run_id: Uuid) -> Result<(), AppError> {
        let mut leases = self.leases.write().await;
        let pos = leases
            .iter()
            .position(|l| l.run_id == run_id)
            .ok_or_else(|| AppError::NotFound("Egress lease not found".to_owned()))?;
        let lease = leases.remove(pos);
        let mut cancel = lease.cancel.lock().await;
        if let Some(sender) = cancel.take() {
            let _ = sender.send(());
        }
        info!(%run_id, "egress lease revoked");
        Ok(())
    }

    pub async fn validate_token(
        &self,
        run_id: Uuid,
        token_b64: &str,
    ) -> Result<Arc<EgressLease>, AppError> {
        let leases = self.leases.read().await;
        leases
            .iter()
            .find(|l| l.run_id == run_id && l.token_b64.as_str() == token_b64)
            .cloned()
            .ok_or_else(|| AppError::Unauthorized("EGRESS_TOKEN_INVALID".to_owned()))
    }

    pub async fn validate_token_by_port(
        &self,
        port: u16,
        token_b64: &str,
    ) -> Result<Arc<EgressLease>, AppError> {
        let leases = self.leases.read().await;
        leases
            .iter()
            .find(|l| l.port == port && l.token_b64.as_str() == token_b64)
            .cloned()
            .ok_or_else(|| AppError::Unauthorized("EGRESS_TOKEN_INVALID".to_owned()))
    }

    pub async fn active_count(&self) -> usize {
        self.leases.read().await.len()
    }

    pub async fn cancel_session(&self, session_run_ids: &[Uuid]) -> usize {
        let mut leases = self.leases.write().await;
        let before = leases.len();
        let mut to_remove = Vec::new();
        for (i, lease) in leases.iter().enumerate() {
            if session_run_ids.contains(&lease.run_id) {
                let mut cancel = lease.cancel.lock().await;
                if let Some(sender) = cancel.take() {
                    let _ = sender.send(());
                }
                to_remove.push(i);
            }
        }
        for i in to_remove.into_iter().rev() {
            leases.remove(i);
        }
        before - leases.len()
    }
}

impl Default for EgressBroker {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn create_and_get_lease() {
        let broker = EgressBroker::new();
        let run_id = Uuid::new_v4();
        let mut domains = BTreeSet::new();
        domains.insert(NormalizedDomain::new("api.example.com"));
        let lease = broker.create_lease(run_id, domains).await.unwrap();
        assert_eq!(lease.run_id, run_id);
        assert!(lease.port > 0);
        assert_eq!(lease.token_b64.len(), 44);
        assert!(broker.active_count().await == 1);
    }

    #[tokio::test]
    async fn get_lease_by_port() {
        let broker = EgressBroker::new();
        let run_id = Uuid::new_v4();
        let lease = broker.create_lease(run_id, BTreeSet::new()).await.unwrap();
        let found = broker.get_lease_by_port(lease.port).await;
        assert!(found.is_some());
        assert_eq!(found.unwrap().run_id, run_id);
    }

    #[tokio::test]
    async fn revoke_lease_removes_it() {
        let broker = EgressBroker::new();
        let run_id = Uuid::new_v4();
        broker.create_lease(run_id, BTreeSet::new()).await.unwrap();
        assert!(broker.revoke_lease(run_id).await.is_ok());
        assert!(broker.active_count().await == 0);
    }

    #[tokio::test]
    async fn revoke_nonexistent_fails() {
        let broker = EgressBroker::new();
        assert!(broker.revoke_lease(Uuid::new_v4()).await.is_err());
    }

    #[tokio::test]
    async fn validate_token_ok() {
        let broker = EgressBroker::new();
        let run_id = Uuid::new_v4();
        let lease = broker.create_lease(run_id, BTreeSet::new()).await.unwrap();
        let result = broker.validate_token(run_id, &lease.token_b64).await;
        assert!(result.is_ok());
    }

    #[tokio::test]
    async fn validate_token_wrong() {
        let broker = EgressBroker::new();
        let run_id = Uuid::new_v4();
        broker.create_lease(run_id, BTreeSet::new()).await.unwrap();
        assert!(broker.validate_token(run_id, "wrong-token").await.is_err());
    }

    #[test]
    fn proxy_url_format() {
        let rt = tokio::runtime::Runtime::new().unwrap();
        let broker = EgressBroker::new();
        let run_id = Uuid::new_v4();
        let lease = rt
            .block_on(broker.create_lease(run_id, BTreeSet::new()))
            .unwrap();
        let url = lease.proxy_url();
        assert!(url.contains("ibreeze:"));
        assert!(url.contains("127.0.0.1"));
    }
}
