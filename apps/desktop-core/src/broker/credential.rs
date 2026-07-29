use serde::{Deserialize, Serialize};
use uuid::Uuid;
use zeroize::Zeroizing;

use keyring::Entry;

use crate::error::AppError;

const KEYCHAIN_SERVICE: &str = "com.ibreeze.desktop";

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct KeychainCredential {
    pub schema_version: u8,
    pub provider_id: Uuid,
    pub auth_type: CredentialAuthType,
    pub secret: Zeroizing<String>,
    pub created_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum CredentialAuthType {
    #[serde(rename = "bearer")]
    Bearer,
    #[serde(rename = "x_api_key")]
    XApiKey,
}

impl CredentialAuthType {
    pub fn as_str(&self) -> &'static str {
        match self {
            CredentialAuthType::Bearer => "Bearer",
            CredentialAuthType::XApiKey => "X-Api-Key",
        }
    }
}

pub struct CredentialStore {}

impl CredentialStore {
    pub fn new() -> Self {
        Self {}
    }

    pub fn load_keychain_credential(
        &self,
        profile_directory_id: &str,
        credential_ref: Uuid,
    ) -> Result<KeychainCredential, AppError> {
        let account = format!("{profile_directory_id}/provider/{credential_ref}");
        let entry = Entry::new(KEYCHAIN_SERVICE, &account)
            .map_err(|e| AppError::Storage(format!("Keychain entry failed: {e}")))?;
        let serialized = entry.get_password().map_err(|e| match e {
            keyring::Error::NoEntry => {
                AppError::NotFound(format!("Credential not found: {credential_ref}"))
            }
            _ => AppError::Storage(format!("Keychain read failed: {e}")),
        })?;
        let serialized = Zeroizing::new(serialized);
        let credential: KeychainCredential = serde_json::from_str(&serialized)
            .map_err(|_| AppError::Security("KEYCHAIN_CREDENTIAL_CORRUPT".to_owned()))?;
        if credential.schema_version != 1 {
            return Err(AppError::Security(format!(
                "Unsupported credential schema version: {}",
                credential.schema_version
            )));
        }
        Ok(credential)
    }

    pub fn store_credential(
        &self,
        profile_directory_id: &str,
        credential_ref: Uuid,
        credential: &KeychainCredential,
    ) -> Result<(), AppError> {
        let account = format!("{profile_directory_id}/provider/{credential_ref}");
        let entry = Entry::new(KEYCHAIN_SERVICE, &account)
            .map_err(|e| AppError::Storage(format!("Keychain entry failed: {e}")))?;
        let serialized =
            serde_json::to_string(credential).map_err(|e| AppError::Internal(e.to_string()))?;
        entry
            .set_password(&serialized)
            .map_err(|e| AppError::Storage(format!("Keychain write failed: {e}")))?;
        Ok(())
    }

    pub fn delete_credential(
        &self,
        profile_directory_id: &str,
        credential_ref: Uuid,
    ) -> Result<bool, AppError> {
        let account = format!("{profile_directory_id}/provider/{credential_ref}");
        let entry = Entry::new(KEYCHAIN_SERVICE, &account)
            .map_err(|e| AppError::Storage(format!("Keychain entry failed: {e}")))?;
        match entry.delete_credential() {
            Ok(()) => Ok(true),
            Err(keyring::Error::NoEntry) => Ok(false),
            Err(e) => Err(AppError::Storage(format!("Keychain delete failed: {e}"))),
        }
    }
}

impl Default for CredentialStore {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn auth_type_strings() {
        assert_eq!(CredentialAuthType::Bearer.as_str(), "Bearer");
        assert_eq!(CredentialAuthType::XApiKey.as_str(), "X-Api-Key");
    }

    #[test]
    fn credential_serialization_roundtrip() {
        let credential = KeychainCredential {
            schema_version: 1,
            provider_id: Uuid::new_v4(),
            auth_type: CredentialAuthType::Bearer,
            secret: Zeroizing::new("sk-test-secret-key".to_owned()),
            created_at: "2026-01-01T00:00:00Z".to_owned(),
        };
        let json = serde_json::to_string(&credential).unwrap();
        let deserialized: KeychainCredential = serde_json::from_str(&json).unwrap();
        assert_eq!(deserialized.schema_version, 1);
        assert_eq!(deserialized.auth_type, CredentialAuthType::Bearer);
    }

    #[test]
    fn credential_rejects_extra_fields() {
        let json = r#"{"schema_version":1,"provider_id":"00000000-0000-4000-8000-000000000001","auth_type":"bearer","secret":"sk-test","created_at":"2026-01-01T00:00:00Z","extra":"bad"}"#;
        assert!(serde_json::from_str::<KeychainCredential>(json).is_err());
    }

    #[test]
    fn credential_rejects_invalid_auth_type() {
        let json = r#"{"schema_version":1,"provider_id":"00000000-0000-4000-8000-000000000001","auth_type":"invalid","secret":"sk-test","created_at":"2026-01-01T00:00:00Z"}"#;
        assert!(serde_json::from_str::<KeychainCredential>(json).is_err());
    }
}
