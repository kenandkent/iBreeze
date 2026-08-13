use std::collections::HashMap;
use std::time::Instant;

use tokio::sync::RwLock;
use uuid::Uuid;

use crate::error::AppError;

#[derive(Debug, Clone)]
pub struct CredentialLease {
    pub lease_id: Uuid,
    pub credential_ref: Uuid,
    pub request_id: Uuid,
    pub run_id: Uuid,
    pub provider_release_id: Uuid,
    pub model_binding_id: Uuid,
    pub created_at: Instant,
    pub expires_at: Instant,
}

pub struct CredentialLeaseManager {
    leases: RwLock<HashMap<Uuid, CredentialLease>>,
    ttl_seconds: u64,
}

impl CredentialLeaseManager {
    pub fn new(ttl_seconds: u64) -> Self {
        Self {
            leases: RwLock::new(HashMap::new()),
            ttl_seconds,
        }
    }

    pub async fn create_lease(
        &self,
        credential_ref: Uuid,
        request_id: Uuid,
        run_id: Uuid,
        provider_release_id: Uuid,
        model_binding_id: Uuid,
    ) -> CredentialLease {
        let now = Instant::now();
        let lease = CredentialLease {
            lease_id: Uuid::new_v4(),
            credential_ref,
            request_id,
            run_id,
            provider_release_id,
            model_binding_id,
            created_at: now,
            expires_at: now + std::time::Duration::from_secs(self.ttl_seconds),
        };
        self.leases
            .write()
            .await
            .insert(lease.lease_id, lease.clone());
        lease
    }

    pub async fn get_lease(&self, lease_id: Uuid) -> Option<CredentialLease> {
        let leases = self.leases.read().await;
        leases.get(&lease_id).cloned()
    }

    pub async fn revoke_lease(&self, lease_id: Uuid) -> Result<(), AppError> {
        self.leases
            .write()
            .await
            .remove(&lease_id)
            .ok_or_else(|| AppError::NotFound("Credential lease not found".to_owned()))?;
        Ok(())
    }

    pub async fn revoke_by_run(&self, run_id: Uuid) -> usize {
        let mut leases = self.leases.write().await;
        let before = leases.len();
        leases.retain(|_, l| l.run_id != run_id);
        before - leases.len()
    }

    pub async fn active_count(&self) -> usize {
        self.leases.read().await.len()
    }

    pub async fn active_for_credential(&self, credential_ref: Uuid) -> usize {
        self.leases
            .read()
            .await
            .values()
            .filter(|lease| lease.credential_ref == credential_ref)
            .count()
    }

    pub async fn cleanup_expired(&self) -> usize {
        let now = Instant::now();
        let mut leases = self.leases.write().await;
        let before = leases.len();
        leases.retain(|_, l| l.expires_at > now);
        before - leases.len()
    }
}

impl Default for CredentialLeaseManager {
    fn default() -> Self {
        Self::new(300)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn create_and_get_lease() {
        let manager = CredentialLeaseManager::new(300);
        let lease = manager
            .create_lease(
                Uuid::new_v4(),
                Uuid::new_v4(),
                Uuid::new_v4(),
                Uuid::new_v4(),
                Uuid::new_v4(),
            )
            .await;
        assert_eq!(manager.active_count().await, 1);
        let fetched = manager.get_lease(lease.lease_id).await;
        assert!(fetched.is_some());
        assert_eq!(fetched.unwrap().lease_id, lease.lease_id);
    }

    #[tokio::test]
    async fn revoke_lease_removes_it() {
        let manager = CredentialLeaseManager::new(300);
        let lease = manager
            .create_lease(
                Uuid::new_v4(),
                Uuid::new_v4(),
                Uuid::new_v4(),
                Uuid::new_v4(),
                Uuid::new_v4(),
            )
            .await;
        assert!(manager.revoke_lease(lease.lease_id).await.is_ok());
        assert_eq!(manager.active_count().await, 0);
    }

    #[tokio::test]
    async fn revoke_by_run_removes_all_for_run() {
        let manager = CredentialLeaseManager::new(300);
        let run_id = Uuid::new_v4();
        manager
            .create_lease(
                Uuid::new_v4(),
                Uuid::new_v4(),
                run_id,
                Uuid::new_v4(),
                Uuid::new_v4(),
            )
            .await;
        manager
            .create_lease(
                Uuid::new_v4(),
                Uuid::new_v4(),
                run_id,
                Uuid::new_v4(),
                Uuid::new_v4(),
            )
            .await;
        manager
            .create_lease(
                Uuid::new_v4(),
                Uuid::new_v4(),
                Uuid::new_v4(),
                Uuid::new_v4(),
                Uuid::new_v4(),
            )
            .await;
        assert_eq!(manager.revoke_by_run(run_id).await, 2);
        assert_eq!(manager.active_count().await, 1);
    }

    #[tokio::test]
    async fn revoke_nonexistent_lease_fails() {
        let manager = CredentialLeaseManager::new(300);
        assert!(manager.revoke_lease(Uuid::new_v4()).await.is_err());
    }
}
