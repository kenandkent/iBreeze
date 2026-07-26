use tokio::sync::RwLock;
use uuid::Uuid;

use crate::error::AppError;

#[derive(Debug, Clone)]
pub struct EgressLease {
    pub run_id: Uuid,
    pub proxy_port: u16,
    pub allowed_domains: Vec<String>,
    pub token: Vec<u8>,
    pub created_at: std::time::Instant,
    pub cancelled: bool,
}

pub struct EgressBroker {
    leases: RwLock<Vec<EgressLease>>,
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
        allowed_domains: Vec<String>,
    ) -> Result<EgressLease, AppError> {
        let leases = self.leases.read().await;
        if leases.iter().any(|l| l.run_id == run_id && !l.cancelled) {
            return Err(AppError::Validation(
                "Run already has an active egress lease".to_owned(),
            ));
        }
        let token = uuid::Uuid::new_v4().to_string().into_bytes();
        let lease = EgressLease {
            run_id,
            proxy_port: 0,
            allowed_domains,
            token,
            created_at: std::time::Instant::now(),
            cancelled: false,
        };
        drop(leases);
        self.leases.write().await.push(lease.clone());
        Ok(lease)
    }

    pub async fn cancel_lease(&self, run_id: Uuid) -> Result<(), AppError> {
        let mut leases = self.leases.write().await;
        if let Some(lease) = leases
            .iter_mut()
            .find(|l| l.run_id == run_id && !l.cancelled)
        {
            lease.cancelled = true;
            Ok(())
        } else {
            Err(AppError::NotFound(
                "No active egress lease for this run".to_owned(),
            ))
        }
    }

    pub async fn validate_token(&self, run_id: Uuid, token: &[u8]) -> Result<(), AppError> {
        let leases = self.leases.read().await;
        let lease = leases
            .iter()
            .find(|l| l.run_id == run_id && !l.cancelled)
            .ok_or_else(|| AppError::Unauthorized("No active egress lease".to_owned()))?;
        if lease.token == token {
            Ok(())
        } else {
            Err(AppError::Unauthorized("Invalid egress token".to_owned()))
        }
    }

    pub async fn validate_url(&self, url: &str, run_id: Uuid) -> Result<(), AppError> {
        let leases = self.leases.read().await;
        let lease = leases
            .iter()
            .find(|l| l.run_id == run_id && !l.cancelled)
            .ok_or_else(|| {
                AppError::NotFound("No active egress lease for this run".to_owned())
            })?;
        super::ssrf_guard::validate_outbound_url(url, &lease.allowed_domains).await
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
    async fn egress_lease_creation_and_cancellation() {
        let broker = EgressBroker::new();
        let run_id = Uuid::new_v4();
        let lease = broker
            .create_lease(run_id, vec!["api.example.com".to_owned()])
            .await
            .expect("create lease");
        assert_eq!(lease.run_id, run_id);
        assert!(!lease.cancelled);
        broker.cancel_lease(run_id).await.expect("cancel lease");
        assert!(broker.cancel_lease(run_id).await.is_err());
    }

    #[tokio::test]
    async fn duplicate_lease_for_same_run_is_rejected() {
        let broker = EgressBroker::new();
        let run_id = Uuid::new_v4();
        broker
            .create_lease(run_id, vec![])
            .await
            .expect("first lease");
        assert!(broker.create_lease(run_id, vec![]).await.is_err());
    }

    #[tokio::test]
    async fn token_validation() {
        let broker = EgressBroker::new();
        let run_id = Uuid::new_v4();
        let lease = broker
            .create_lease(run_id, vec![])
            .await
            .expect("create lease");
        assert!(broker.validate_token(run_id, &lease.token).await.is_ok());
        assert!(broker.validate_token(run_id, b"wrong-token").await.is_err());
    }
}
