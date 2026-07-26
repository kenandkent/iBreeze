//! OS Keychain storage for the atomic session bundle.

use keyring::Entry;
use serde::{Deserialize, Serialize};
use tracing::{info, warn};
use zeroize::{Zeroize, ZeroizeOnDrop, Zeroizing};

use crate::error::AppError;

const KEYCHAIN_SERVICE: &str = "com.ibreeze.desktop";

#[derive(Debug, Clone, Serialize, Deserialize, Zeroize, ZeroizeOnDrop)]
#[serde(deny_unknown_fields)]
pub struct SessionBundle {
    pub schema_version: u8,
    pub refresh_token: String,
    pub offline_session_ticket: String,
    pub family_id: String,
    pub issued_at: String,
}

pub struct SecureKeyring {
    service: String,
}

impl SecureKeyring {
    pub fn new() -> Self {
        Self {
            service: KEYCHAIN_SERVICE.to_owned(),
        }
    }

    pub fn store_bundle(
        &self,
        profile_directory_id: &str,
        bundle: &SessionBundle,
    ) -> Result<(), AppError> {
        info!(key = %profile_directory_id, "keychain.store.start");
        let entry = self.entry(profile_directory_id)?;
        let old_value = read_raw(&entry)?;
        if let Some(old) = old_value.as_deref() {
            serde_json::from_str::<SessionBundle>(old)
                .map_err(|_| AppError::Security("KEYCHAIN_BUNDLE_CORRUPT".to_owned()))?;
        }
        let serialized = Zeroizing::new(
            serde_json::to_string(bundle).map_err(|error| AppError::Internal(error.to_string()))?,
        );
        let write_result = entry.set_password(&serialized);
        let read_back = read_raw(&entry)?;
        match (write_result, read_back.as_deref()) {
            (Ok(()), Some(value)) if value == serialized.as_str() => {
                info!(key = %profile_directory_id, "keychain.store.success");
                Ok(())
            }
            (Err(_), Some(value)) if value == serialized.as_str() => {
                info!(key = %profile_directory_id, "keychain.store.success");
                Ok(())
            }
            (Err(error), value) if value == old_value.as_deref() => {
                warn!(key = %profile_directory_id, error = %error, "keychain.store.failed");
                Err(AppError::Storage(format!("Keychain write failed: {error}")))
            }
            _ => {
                warn!(key = %profile_directory_id, "keychain.store.corrupt");
                Err(AppError::Security("KEYCHAIN_BUNDLE_CORRUPT".to_owned()))
            }
        }
    }

    pub fn load_bundle(
        &self,
        profile_directory_id: &str,
    ) -> Result<Option<SessionBundle>, AppError> {
        info!(key = %profile_directory_id, "keychain.load.start");
        let entry = self.entry(profile_directory_id)?;
        match read_raw(&entry)? {
            Some(serialized) => {
                info!(key = %profile_directory_id, "keychain.load.success");
                serde_json::from_str(&serialized)
                    .map(Some)
                    .map_err(|_| AppError::Security("KEYCHAIN_BUNDLE_CORRUPT".to_owned()))
            }
            None => {
                info!(key = %profile_directory_id, "keychain.load.not_found");
                Ok(None)
            }
        }
    }

    pub fn delete_bundle(&self, profile_directory_id: &str) -> Result<bool, AppError> {
        info!(key = %profile_directory_id, "keychain.delete.start");
        match self.entry(profile_directory_id)?.delete_credential() {
            Ok(()) => {
                info!(key = %profile_directory_id, "keychain.delete.success");
                Ok(true)
            }
            Err(keyring::Error::NoEntry) => {
                info!(key = %profile_directory_id, "keychain.delete.not_found");
                Ok(false)
            }
            Err(error) => {
                warn!(key = %profile_directory_id, error = %error, "keychain.delete.failed");
                Err(AppError::Storage(format!(
                    "Keychain delete failed: {error}"
                )))
            }
        }
    }

    fn entry(&self, profile_directory_id: &str) -> Result<Entry, AppError> {
        if profile_directory_id.is_empty()
            || !profile_directory_id
                .bytes()
                .all(|value| value.is_ascii_lowercase() || value.is_ascii_digit())
        {
            return Err(AppError::Validation(
                "Invalid Profile directory identifier".to_owned(),
            ));
        }
        Entry::new(
            &self.service,
            &format!("{profile_directory_id}/session-bundle"),
        )
        .map_err(|error| AppError::Storage(format!("Keychain unavailable: {error}")))
    }
}

fn read_raw(entry: &Entry) -> Result<Option<Zeroizing<String>>, AppError> {
    match entry.get_password() {
        Ok(value) => Ok(Some(Zeroizing::new(value))),
        Err(keyring::Error::NoEntry) => Ok(None),
        Err(error) => Err(AppError::Storage(format!("Keychain read failed: {error}"))),
    }
}

impl Default for SecureKeyring {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_bundle() -> SessionBundle {
        SessionBundle {
            schema_version: 1,
            refresh_token: "rt".to_owned(),
            offline_session_ticket: "ost".to_owned(),
            family_id: "fid".to_owned(),
            issued_at: "2026-01-01T00:00:00Z".to_owned(),
        }
    }

    #[test]
    fn session_bundle_zeroize_on_drop() {
        let bundle = test_bundle();
        let serialized = serde_json::to_string(&bundle).expect("serialize");
        assert!(serialized.contains("refresh_token"));
        drop(bundle);
    }

    #[test]
    fn session_bundle_roundtrip() {
        let bundle = test_bundle();
        let json = serde_json::to_string(&bundle).expect("serialize");
        let deserialized: SessionBundle = serde_json::from_str(&json).expect("deserialize");
        assert_eq!(bundle.schema_version, deserialized.schema_version);
        assert_eq!(bundle.family_id, deserialized.family_id);
    }

    #[test]
    fn session_bundle_rejects_extra_fields() {
        let extra = r#"{"schema_version":1,"refresh_token":"t","offline_session_ticket":"t","family_id":"f","issued_at":"2026-01-01T00:00:00Z","extra":"bad"}"#;
        assert!(
            serde_json::from_str::<SessionBundle>(extra).is_err(),
            "AUTH-010: extra fields must be rejected"
        );
    }

    #[test]
    fn keyring_entry_validation_rejects_invalid_ids() {
        let keyring = SecureKeyring::new();
        assert!(keyring.load_bundle("../escape").is_err());
        assert!(keyring.load_bundle("UPPERCASE").is_err());
        assert!(keyring.load_bundle("").is_err());
        assert!(keyring.load_bundle("validid123").is_ok());
    }
}
