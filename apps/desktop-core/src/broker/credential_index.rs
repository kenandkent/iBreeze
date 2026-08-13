use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use uuid::Uuid;

use crate::error::AppError;

fn normalize_label(value: &str) -> String {
    use unicode_normalization::UnicodeNormalization;
    value.trim().nfkc().flat_map(char::to_lowercase).collect()
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum CredentialState {
    Creating,
    Updating,
    Unverified,
    Ready,
    Deleting,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CredentialMetadata {
    pub credential_ref: Uuid,
    pub label: String,
    pub normalized_label: String,
    pub provider_release_id: Uuid,
    pub auth_type: String,
    pub state: CredentialState,
    pub resume_state: Option<CredentialState>,
    pub metadata_version: u64,
    pub active_secret_version: Option<u64>,
    pub pending_secret_version: Option<u64>,
    pub created_at: String,
    pub updated_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CredentialIndex {
    pub schema_version: u8,
    pub revision: u64,
    pub credentials: Vec<CredentialMetadata>,
}

impl Default for CredentialIndex {
    fn default() -> Self {
        Self {
            schema_version: 1,
            revision: 0,
            credentials: Vec::new(),
        }
    }
}

pub struct CredentialIndexStore {
    path: PathBuf,
}

impl CredentialIndexStore {
    pub fn new(profile_root: impl AsRef<Path>) -> Self {
        Self {
            path: profile_root.as_ref().join("provider-credentials.v1.json"),
        }
    }

    pub fn load(&self) -> Result<CredentialIndex, AppError> {
        if !self.path.exists() {
            return Ok(CredentialIndex::default());
        }
        let bytes = fs::read(&self.path).map_err(|e| AppError::Storage(e.to_string()))?;
        let index: CredentialIndex = serde_json::from_slice(&bytes)
            .map_err(|_| AppError::Security("CREDENTIAL_INDEX_CORRUPT".to_owned()))?;
        self.validate(&index)?;
        Ok(index)
    }

    pub fn save(&self, mut index: CredentialIndex) -> Result<(), AppError> {
        self.validate(&index)?;
        index.revision = index.revision.saturating_add(1);
        let parent = self
            .path
            .parent()
            .ok_or_else(|| AppError::Storage("credential index parent missing".to_owned()))?;
        fs::create_dir_all(parent).map_err(|e| AppError::Storage(e.to_string()))?;
        let tmp = self.path.with_extension("json.tmp");
        let bytes =
            serde_json::to_vec_pretty(&index).map_err(|e| AppError::Internal(e.to_string()))?;
        let mut file = OpenOptions::new()
            .create(true)
            .truncate(true)
            .write(true)
            .open(&tmp)
            .map_err(|e| AppError::Storage(e.to_string()))?;
        file.write_all(&bytes)
            .map_err(|e| AppError::Storage(e.to_string()))?;
        file.sync_all()
            .map_err(|e| AppError::Storage(e.to_string()))?;
        drop(file);
        fs::rename(&tmp, &self.path).map_err(|e| AppError::Storage(e.to_string()))?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            fs::set_permissions(&self.path, fs::Permissions::from_mode(0o600))
                .map_err(|e| AppError::Storage(e.to_string()))?;
        }
        Ok(())
    }

    fn validate(&self, index: &CredentialIndex) -> Result<(), AppError> {
        if index.schema_version != 1
            || index.credentials.iter().any(|item| {
                item.label.trim().is_empty()
                    || item.normalized_label != normalize_label(&item.label)
                    || item.metadata_version == 0
                    || item
                        .active_secret_version
                        .is_some_and(|version| version == 0)
                    || item
                        .pending_secret_version
                        .is_some_and(|version| version == 0)
                    || !matches!(item.auth_type.as_str(), "bearer" | "x_api_key")
            })
        {
            return Err(AppError::Security("CREDENTIAL_INDEX_CORRUPT".to_owned()));
        }
        let mut labels = std::collections::BTreeSet::new();
        for item in &index.credentials {
            if !matches!(item.state, CredentialState::Deleting)
                && !labels.insert((item.provider_release_id, item.normalized_label.clone()))
            {
                return Err(AppError::Security("CREDENTIAL_INDEX_CORRUPT".to_owned()));
            }
        }
        for item in &index.credentials {
            match item.state {
                CredentialState::Creating => {
                    if item.active_secret_version.is_some()
                        || item.pending_secret_version != Some(1)
                        || item.resume_state.is_some()
                    {
                        return Err(AppError::Security("CREDENTIAL_INDEX_CORRUPT".to_owned()));
                    }
                }
                CredentialState::Updating => {
                    if item.active_secret_version.is_none()
                        || item.pending_secret_version != item.active_secret_version.map(|v| v + 1)
                        || item.resume_state.is_none()
                    {
                        return Err(AppError::Security("CREDENTIAL_INDEX_CORRUPT".to_owned()));
                    }
                }
                CredentialState::Unverified | CredentialState::Ready => {
                    if item.active_secret_version.is_none()
                        || item.pending_secret_version.is_some()
                        || item.resume_state.is_some()
                    {
                        return Err(AppError::Security("CREDENTIAL_INDEX_CORRUPT".to_owned()));
                    }
                }
                CredentialState::Deleting => {
                    if item.active_secret_version.is_none()
                        || item.pending_secret_version.is_some()
                        || item.resume_state.is_none()
                    {
                        return Err(AppError::Security("CREDENTIAL_INDEX_CORRUPT".to_owned()));
                    }
                }
            }
        }
        Ok(())
    }
}
