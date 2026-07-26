use std::collections::HashMap;
use tokio::sync::RwLock;
use zeroize::Zeroizing;

use crate::error::AppError;

#[derive(Default)]
pub struct CredentialBroker {
    credentials: RwLock<HashMap<String, Zeroizing<String>>>,
}

impl CredentialBroker {
    pub fn new() -> Self {
        Self {
            credentials: RwLock::new(HashMap::new()),
        }
    }

    pub async fn register_credential(&self, credential_ref: &str, api_key: Zeroizing<String>) {
        self.credentials
            .write()
            .await
            .insert(credential_ref.to_owned(), api_key);
    }

    pub async fn resolve_credential(&self, credential_ref: &str) -> Result<String, AppError> {
        let creds = self.credentials.read().await;
        creds
            .get(credential_ref)
            .map(|k| k.to_string())
            .ok_or_else(|| AppError::NotFound(format!("Credential not found: {credential_ref}")))
    }

    pub async fn unregister_credential(&self, credential_ref: &str) {
        self.credentials.write().await.remove(credential_ref);
    }
}
