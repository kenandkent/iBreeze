//! Non-secret application paths, installation metadata, and Profile discovery metadata.

use std::fs::{File, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};

use data_encoding::BASE32_NOPAD;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use uuid::Uuid;

use crate::error::AppError;

#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct InstallationMeta {
    device_id: Uuid,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct ProfileMeta {
    pub schema_version: u8,
    pub profile_directory_id: String,
    pub backend_origin: String,
    pub app_user_id: Uuid,
    pub masked_identifier: String,
}

pub struct LocalStore {
    base_path: PathBuf,
}

impl LocalStore {
    pub fn new(base_path: PathBuf) -> Self {
        Self { base_path }
    }

    pub fn profiles_path(&self) -> PathBuf {
        self.base_path.join("profiles")
    }

    pub fn runtime_path(&self) -> PathBuf {
        self.base_path.join("runtime")
    }

    pub fn profile_path(&self, profile_directory_id: &str) -> Result<PathBuf, AppError> {
        if profile_directory_id.is_empty()
            || !profile_directory_id
                .bytes()
                .all(|value| value.is_ascii_lowercase() || value.is_ascii_digit())
        {
            return Err(AppError::Validation(
                "Invalid Profile directory identifier".to_owned(),
            ));
        }
        Ok(self.profiles_path().join(profile_directory_id))
    }

    pub fn initialize(&self) -> Result<Uuid, AppError> {
        create_private_directory(&self.base_path)?;
        create_private_directory(&self.profiles_path())?;
        create_private_directory(&self.runtime_path())?;
        let metadata_path = self.base_path.join("installation.json");
        if metadata_path.exists() {
            let bytes = std::fs::read(&metadata_path)
                .map_err(|error| AppError::Storage(error.to_string()))?;
            let metadata: InstallationMeta = serde_json::from_slice(&bytes)
                .map_err(|_| AppError::Security("Installation metadata is corrupt".to_owned()))?;
            return Ok(metadata.device_id);
        }
        let metadata = InstallationMeta {
            device_id: Uuid::new_v4(),
        };
        let bytes =
            serde_json::to_vec(&metadata).map_err(|error| AppError::Internal(error.to_string()))?;
        let temporary = self
            .base_path
            .join(format!(".installation-{}.tmp", Uuid::new_v4()));
        atomic_private_write(&temporary, &metadata_path, &bytes)?;
        Ok(metadata.device_id)
    }

    pub fn write_profile_meta(&self, meta: &ProfileMeta) -> Result<(), AppError> {
        validate_profile_meta(meta)?;
        let profile_path = self.profile_path(&meta.profile_directory_id)?;
        create_private_directory(&profile_path)?;
        let destination = profile_path.join("profile-meta.v1.json");
        let temporary = profile_path.join(format!(".profile-meta-{}.tmp", Uuid::new_v4()));
        let bytes =
            serde_json::to_vec(meta).map_err(|error| AppError::Internal(error.to_string()))?;
        atomic_private_write(&temporary, &destination, &bytes)
    }

    pub fn list_profile_meta(&self) -> Result<Vec<ProfileMeta>, AppError> {
        let mut result = Vec::new();
        for entry in std::fs::read_dir(self.profiles_path())
            .map_err(|error| AppError::Storage(error.to_string()))?
        {
            let entry = entry.map_err(|error| AppError::Storage(error.to_string()))?;
            let file_type = entry
                .file_type()
                .map_err(|error| AppError::Storage(error.to_string()))?;
            if !file_type.is_dir() {
                continue;
            }
            let directory_name = match entry.file_name().to_str() {
                Some(value) => value.to_owned(),
                None => continue,
            };
            let bytes = match std::fs::read(entry.path().join("profile-meta.v1.json")) {
                Ok(value) => value,
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => continue,
                Err(_) => continue,
            };
            let meta: ProfileMeta = match serde_json::from_slice(&bytes) {
                Ok(value) => value,
                Err(_) => continue,
            };
            if meta.profile_directory_id == directory_name && validate_profile_meta(&meta).is_ok() {
                result.push(meta);
            }
        }
        result.sort_by(|left, right| {
            left.backend_origin
                .cmp(&right.backend_origin)
                .then(left.masked_identifier.cmp(&right.masked_identifier))
        });
        Ok(result)
    }

    pub fn write_profile_document(
        &self,
        profile_directory_id: &str,
        name: &str,
        bytes: &[u8],
    ) -> Result<(), AppError> {
        validate_profile_document_name(name)?;
        let profile_path = self.profile_path(profile_directory_id)?;
        create_private_directory(&profile_path)?;
        let destination = profile_path.join(name);
        let temporary = profile_path.join(format!(".{name}-{}.tmp", Uuid::new_v4()));
        atomic_private_write(&temporary, &destination, bytes)
    }

    pub fn read_profile_document(
        &self,
        profile_directory_id: &str,
        name: &str,
    ) -> Result<Vec<u8>, AppError> {
        validate_profile_document_name(name)?;
        std::fs::read(self.profile_path(profile_directory_id)?.join(name))
            .map_err(|error| AppError::Storage(error.to_string()))
    }
}

pub fn profile_directory_id(origin: &str, user_id: Uuid) -> String {
    let mut digest = Sha256::new();
    digest.update(origin.as_bytes());
    digest.update([0]);
    digest.update(user_id.to_string().as_bytes());
    BASE32_NOPAD.encode(&digest.finalize()).to_ascii_lowercase()
}

fn validate_profile_meta(meta: &ProfileMeta) -> Result<(), AppError> {
    if meta.schema_version != 1
        || meta.backend_origin.is_empty()
        || meta.backend_origin.len() > 2048
        || meta.masked_identifier.is_empty()
        || meta.masked_identifier.len() > 320
        || meta.profile_directory_id != profile_directory_id(&meta.backend_origin, meta.app_user_id)
    {
        return Err(AppError::Security(
            "Profile discovery metadata is invalid".to_owned(),
        ));
    }
    Ok(())
}

fn validate_profile_document_name(name: &str) -> Result<(), AppError> {
    if !matches!(
        name,
        "catalog-keyset.v1.json" | "auth-keyset.v1.json" | "catalog-manifest.v1.json"
    ) {
        return Err(AppError::Validation(
            "Invalid Profile document name".to_owned(),
        ));
    }
    Ok(())
}

fn atomic_private_write(
    temporary: &Path,
    destination: &Path,
    bytes: &[u8],
) -> Result<(), AppError> {
    #[cfg(unix)]
    use std::os::unix::fs::OpenOptionsExt;

    let mut options = OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    options.mode(0o600);
    let mut file = options
        .open(temporary)
        .map_err(|error| AppError::Storage(error.to_string()))?;
    if let Err(error) = (|| -> std::io::Result<()> {
        file.write_all(bytes)?;
        file.sync_all()?;
        std::fs::rename(temporary, destination)?;
        if let Some(parent) = destination.parent() {
            File::open(parent)?.sync_all()?;
        }
        Ok(())
    })() {
        let _ = std::fs::remove_file(temporary);
        return Err(AppError::Storage(error.to_string()));
    }
    Ok(())
}

#[cfg(unix)]
fn create_private_directory(path: &Path) -> Result<(), AppError> {
    use std::os::unix::fs::PermissionsExt;

    std::fs::create_dir_all(path).map_err(|error| AppError::Storage(error.to_string()))?;
    std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o700))
        .map_err(|error| AppError::Storage(error.to_string()))
}

#[cfg(not(unix))]
fn create_private_directory(path: &Path) -> Result<(), AppError> {
    std::fs::create_dir_all(path).map_err(|error| AppError::Storage(error.to_string()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn installation_identifier_is_stable() {
        let directory = tempfile::tempdir().expect("temporary directory");
        let store = LocalStore::new(directory.path().join("ibreeze"));
        let first = store.initialize().expect("initialize");
        let second = store.initialize().expect("re-open");
        assert_eq!(first, second);
        assert!(store.profiles_path().is_dir());
        assert!(store.runtime_path().is_dir());
    }

    #[test]
    fn profile_path_rejects_traversal() {
        let directory = tempfile::tempdir().expect("temporary directory");
        let store = LocalStore::new(directory.path().to_path_buf());
        assert!(store.profile_path("../escape").is_err());
    }

    #[test]
    fn profile_metadata_is_atomic_and_invalid_entries_are_ignored() {
        let directory = tempfile::tempdir().expect("temporary directory");
        let store = LocalStore::new(directory.path().join("ibreeze"));
        store.initialize().expect("initialize");
        let app_user_id = Uuid::new_v4();
        let origin = "https://example.com:443".to_owned();
        let profile_directory_id = profile_directory_id(&origin, app_user_id);
        let meta = ProfileMeta {
            schema_version: 1,
            profile_directory_id: profile_directory_id.clone(),
            backend_origin: origin,
            app_user_id,
            masked_identifier: "u***@example.com".to_owned(),
        };
        store.write_profile_meta(&meta).expect("write meta");
        assert_eq!(store.list_profile_meta().expect("list"), vec![meta]);

        let invalid_directory = store.profiles_path().join("invalid");
        create_private_directory(&invalid_directory).expect("invalid directory");
        std::fs::write(invalid_directory.join("profile-meta.v1.json"), b"{}")
            .expect("invalid meta");
        assert_eq!(store.list_profile_meta().expect("list").len(), 1);
    }
}
