//! OS Keychain storage for the atomic session bundle.

use keyring::Entry;
use serde::{Deserialize, Serialize};
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
            (Ok(()), Some(value)) if value == serialized.as_str() => Ok(()),
            (Err(_), Some(value)) if value == serialized.as_str() => Ok(()),
            (Err(error), value) if value == old_value.as_deref() => {
                Err(AppError::Storage(format!("Keychain write failed: {error}")))
            }
            _ => Err(AppError::Security("KEYCHAIN_BUNDLE_CORRUPT".to_owned())),
        }
    }

    pub fn load_bundle(
        &self,
        profile_directory_id: &str,
    ) -> Result<Option<SessionBundle>, AppError> {
        let entry = self.entry(profile_directory_id)?;
        match read_raw(&entry)? {
            Some(serialized) => serde_json::from_str(&serialized)
                .map(Some)
                .map_err(|_| AppError::Security("KEYCHAIN_BUNDLE_CORRUPT".to_owned())),
            None => Ok(None),
        }
    }

    pub fn delete_bundle(&self, profile_directory_id: &str) -> Result<bool, AppError> {
        match self.entry(profile_directory_id)?.delete_credential() {
            Ok(()) => Ok(true),
            Err(keyring::Error::NoEntry) => Ok(false),
            Err(error) => Err(AppError::Storage(format!(
                "Keychain delete failed: {error}"
            ))),
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
