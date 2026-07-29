use std::path::{Path, PathBuf};

use base64::Engine;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use tracing::{info, warn};
use uuid::Uuid;

use crate::error::AppError;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PendingUpdateMarker {
    pub old_version: String,
    pub new_version: String,
    pub backup_id: String,
    pub stable_package_sha: String,
    pub created_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StableMarker {
    pub version: String,
    pub confirmed_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct HealthObservation {
    started_at: String,
}

pub struct UpdateStore {
    base_path: PathBuf,
}

impl UpdateStore {
    pub fn new(base_path: PathBuf) -> Self {
        Self { base_path }
    }

    pub fn update_root(&self) -> PathBuf {
        self.base_path.join("update")
    }

    pub fn backups_path(&self) -> PathBuf {
        self.update_root().join("backups")
    }

    pub fn pending_marker_path(&self) -> PathBuf {
        self.update_root().join("pending-update.json")
    }

    pub fn stable_marker_path(&self) -> PathBuf {
        self.update_root().join("stable.json")
    }

    pub fn health_observation_path(&self) -> PathBuf {
        self.update_root().join("health-observation.json")
    }

    pub fn ensure_dirs(&self) -> Result<(), AppError> {
        let dirs = [self.update_root(), self.backups_path()];
        for dir in &dirs {
            std::fs::create_dir_all(dir)
                .map_err(|e| AppError::Storage(format!("create update dir: {e}")))?;
        }
        Ok(())
    }

    pub fn cache_current_install(
        &self,
        install_path: &Path,
        app_version: &str,
    ) -> Result<(String, String), AppError> {
        self.ensure_dirs()?;
        let backup_id = Uuid::new_v4().to_string();
        let backup_dir = self.backups_path().join(&backup_id);
        std::fs::create_dir_all(&backup_dir)
            .map_err(|e| AppError::Storage(format!("create backup dir: {e}")))?;
        let backup_archive = backup_dir.join("bundle.tar.gz");
        let status = std::process::Command::new("tar")
            .arg("-czf")
            .arg(&backup_archive)
            .arg("-C")
            .arg(install_path)
            .arg(".")
            .status()
            .map_err(|e| AppError::Io(format!("backup tar failed: {e}")))?;

        if !status.success() {
            let _ = std::fs::remove_dir_all(&backup_dir);
            return Err(AppError::Io("UPDATE_BACKUP_CREATE_FAILED".to_owned()));
        }

        let bytes = std::fs::read(&backup_archive)
            .map_err(|e| AppError::Io(format!("read backup: {e}")))?;
        let mut hasher = Sha256::new();
        hasher.update(&bytes);
        let sha = base64::engine::general_purpose::STANDARD.encode(hasher.finalize());

        info!(backup_id = %backup_id, sha = %sha, version = %app_version, "UPDATE_BACKUP_CREATED");
        Ok((backup_id, sha))
    }

    pub fn safe_extract(package_path: &Path, target_dir: &Path) -> Result<(), AppError> {
        Self::validate_tar_entries(package_path)?;

        let parent = target_dir.parent().unwrap_or(Path::new("."));
        let staging = parent.join(format!(".staging_{}", Uuid::new_v4()));
        std::fs::create_dir_all(&staging)
            .map_err(|e| AppError::Storage(format!("create staging: {e}")))?;

        let status = std::process::Command::new("tar")
            .arg("-xzf")
            .arg(package_path)
            .arg("-C")
            .arg(&staging)
            .status()
            .map_err(|e| AppError::Io(format!("extract: {e}")))?;

        if !status.success() {
            let _ = std::fs::remove_dir_all(&staging);
            return Err(AppError::Io("UPDATE_EXTRACT_FAILED".to_owned()));
        }

        if let Err(e) = Self::validate_extracted(&staging) {
            let _ = std::fs::remove_dir_all(&staging);
            return Err(e);
        }

        let old_dir = parent.join(format!(".old_{}", Uuid::new_v4()));
        if target_dir.exists() {
            std::fs::rename(target_dir, &old_dir)
                .map_err(|e| AppError::Storage(format!("rename old target: {e}")))?;
        }
        if let Err(e) = std::fs::rename(&staging, target_dir) {
            let _ = std::fs::remove_dir_all(&staging);
            if old_dir.exists() {
                let _ = std::fs::rename(&old_dir, target_dir);
            }
            return Err(AppError::Storage(format!("rename: {e}")));
        }
        let _ = std::fs::remove_dir_all(&old_dir);

        Ok(())
    }

    fn validate_tar_entries(package_path: &Path) -> Result<(), AppError> {
        let output = std::process::Command::new("tar")
            .arg("-tzf")
            .arg(package_path)
            .output()
            .map_err(|e| AppError::Io(format!("list entries: {e}")))?;

        if !output.status.success() {
            return Err(AppError::Io("UPDATE_LIST_FAILED".to_owned()));
        }

        let text = String::from_utf8_lossy(&output.stdout);
        for line in text.lines() {
            let line = line.trim();
            if line.is_empty() {
                continue;
            }

            let path_str = line.trim_end_matches('/');
            let path = std::path::Path::new(path_str);
            if path
                .components()
                .any(|c| c == std::path::Component::ParentDir)
            {
                return Err(AppError::Io("UPDATE_PATH_TRAVERSAL_DETECTED".to_owned()));
            }

            if line.contains(" -> ") {
                return Err(AppError::Io("UPDATE_SYMLINK_REJECTED".to_owned()));
            }
        }
        Ok(())
    }

    fn validate_extracted(dir: &Path) -> Result<(), AppError> {
        let canonical_base = dir
            .canonicalize()
            .map_err(|e| AppError::Io(format!("canonicalize: {e}")))?;
        Self::validate_entry(&canonical_base, &canonical_base)
    }

    fn validate_entry(canonical_base: &Path, path: &Path) -> Result<(), AppError> {
        let metadata =
            std::fs::symlink_metadata(path).map_err(|e| AppError::Io(format!("metadata: {e}")))?;

        if metadata.file_type().is_symlink() {
            return Err(AppError::Io("UPDATE_SYMLINK_REJECTED".to_owned()));
        }

        #[cfg(unix)]
        if metadata.is_file() {
            use std::os::unix::fs::MetadataExt;
            if metadata.nlink() > 1 {
                return Err(AppError::Io("UPDATE_HARDLINK_REJECTED".to_owned()));
            }
        }

        if metadata.is_dir() {
            let canonical = path
                .canonicalize()
                .map_err(|e| AppError::Io(format!("canonicalize: {e}")))?;
            if !canonical.starts_with(canonical_base) {
                return Err(AppError::Io("UPDATE_PATH_TRAVERSAL_DETECTED".to_owned()));
            }

            for entry in
                std::fs::read_dir(path).map_err(|e| AppError::Io(format!("read_dir: {e}")))?
            {
                let entry = entry.map_err(|e| AppError::Io(e.to_string()))?;
                Self::validate_entry(canonical_base, &entry.path())?;
            }
        }

        Ok(())
    }

    pub fn create_pending_marker(
        &self,
        old_version: &str,
        new_version: &str,
        backup_id: &str,
        stable_package_sha: &str,
    ) -> Result<(), AppError> {
        self.ensure_dirs()?;
        let marker = PendingUpdateMarker {
            old_version: old_version.to_owned(),
            new_version: new_version.to_owned(),
            backup_id: backup_id.to_owned(),
            stable_package_sha: stable_package_sha.to_owned(),
            created_at: chrono::Utc::now().to_rfc3339(),
        };
        let bytes = serde_json::to_vec(&marker).map_err(|e| AppError::Internal(e.to_string()))?;
        let path = self.pending_marker_path();
        let tmp = path.with_extension(format!("{}.tmp", Uuid::new_v4()));
        std::fs::write(&tmp, &bytes)
            .map_err(|e| AppError::Storage(format!("write pending marker: {e}")))?;
        std::fs::rename(&tmp, &path)
            .map_err(|e| AppError::Storage(format!("commit pending marker: {e}")))?;
        info!(old = %old_version, new = %new_version, "UPDATE_PENDING_MARKER_CREATED");
        Ok(())
    }

    pub fn load_pending_marker(&self) -> Result<Option<PendingUpdateMarker>, AppError> {
        let path = self.pending_marker_path();
        if !path.exists() {
            return Ok(None);
        }
        let bytes = std::fs::read(&path)
            .map_err(|e| AppError::Storage(format!("read pending marker: {e}")))?;
        let marker: PendingUpdateMarker = serde_json::from_slice(&bytes)
            .map_err(|e| AppError::Storage(format!("parse pending marker: {e}")))?;
        Ok(Some(marker))
    }

    pub fn delete_pending_marker(&self) -> Result<(), AppError> {
        let path = self.pending_marker_path();
        if path.exists() {
            std::fs::remove_file(&path)
                .map_err(|e| AppError::Storage(format!("delete pending marker: {e}")))?;
            info!("UPDATE_PENDING_MARKER_DELETED");
        }
        Ok(())
    }

    pub fn mark_stable(&self, version: &str) -> Result<(), AppError> {
        self.ensure_dirs()?;
        let marker = StableMarker {
            version: version.to_owned(),
            confirmed_at: chrono::Utc::now().to_rfc3339(),
        };
        let bytes = serde_json::to_vec(&marker).map_err(|e| AppError::Internal(e.to_string()))?;
        let path = self.stable_marker_path();
        let tmp = path.with_extension(format!("{}.tmp", Uuid::new_v4()));
        std::fs::write(&tmp, &bytes)
            .map_err(|e| AppError::Storage(format!("write stable marker: {e}")))?;
        std::fs::rename(&tmp, &path)
            .map_err(|e| AppError::Storage(format!("commit stable marker: {e}")))?;
        info!(version = %version, "UPDATE_STABLE_MARKED");
        Ok(())
    }

    pub fn load_stable_version(&self) -> Result<Option<String>, AppError> {
        let path = self.stable_marker_path();
        if !path.exists() {
            return Ok(None);
        }
        let bytes = std::fs::read(&path)
            .map_err(|e| AppError::Storage(format!("read stable marker: {e}")))?;
        let marker: StableMarker = serde_json::from_slice(&bytes)
            .map_err(|e| AppError::Storage(format!("parse stable marker: {e}")))?;
        Ok(Some(marker.version))
    }

    pub fn restore_backup(&self, install_path: &Path, backup_id: &str) -> Result<(), AppError> {
        let backup_archive = self.backups_path().join(backup_id).join("bundle.tar.gz");
        if !backup_archive.exists() {
            return Err(AppError::NotFound("UPDATE_BACKUP_NOT_FOUND".to_owned()));
        }
        Self::validate_tar_entries(&backup_archive)?;

        let parent = install_path.parent().unwrap_or(Path::new("."));
        let staging = parent.join(format!(".restore_{}", Uuid::new_v4()));
        std::fs::create_dir_all(&staging)
            .map_err(|e| AppError::Storage(format!("create restore staging: {e}")))?;

        let status = std::process::Command::new("tar")
            .arg("-xzf")
            .arg(&backup_archive)
            .arg("-C")
            .arg(&staging)
            .status()
            .map_err(|e| AppError::Io(format!("restore extract: {e}")))?;

        if !status.success() {
            let _ = std::fs::remove_dir_all(&staging);
            return Err(AppError::Io("UPDATE_BACKUP_RESTORE_EXTRACT_FAILED".to_owned()));
        }

        if let Err(e) = Self::validate_extracted(&staging) {
            let _ = std::fs::remove_dir_all(&staging);
            return Err(e);
        }

        let old_dir = parent.join(format!(".old_restore_{}", Uuid::new_v4()));
        if install_path.exists() {
            std::fs::rename(install_path, &old_dir)
                .map_err(|e| AppError::Storage(format!("rename old install: {e}")))?;
        }
        if let Err(e) = std::fs::rename(&staging, install_path) {
            let _ = std::fs::remove_dir_all(&staging);
            if old_dir.exists() {
                let _ = std::fs::rename(&old_dir, install_path);
            }
            return Err(AppError::Storage(format!("rename restored: {e}")));
        }
        let _ = std::fs::remove_dir_all(&old_dir);

        info!(backup_id = %backup_id, "UPDATE_BACKUP_RESTORED");
        Ok(())
    }

    pub fn verify_pending_update(
        &self,
        sidecar_executable: &Path,
        app_version: &str,
    ) -> Result<bool, AppError> {
        let marker = match self.load_pending_marker()? {
            Some(m) => m,
            None => return Ok(true),
        };

        if !sidecar_executable.exists() {
            warn!("UPDATE_VERIFY_SIDECAR_MISSING");
            return Ok(false);
        }

        if marker.new_version != app_version {
            warn!(expected = %marker.new_version, actual = %app_version, "UPDATE_VERIFY_VERSION_MISMATCH");
            return Ok(false);
        }

        let stable_path = self.stable_marker_path();
        if stable_path.exists() {
            info!("UPDATE_ALREADY_STABLE");
            self.delete_pending_marker()?;
            return Ok(true);
        }

        let obs_path = self.health_observation_path();
        if !obs_path.exists() {
            let obs = HealthObservation {
                started_at: chrono::Utc::now().to_rfc3339(),
            };
            let bytes = serde_json::to_vec(&obs).map_err(|e| AppError::Internal(e.to_string()))?;
            std::fs::write(&obs_path, &bytes)
                .map_err(|e| AppError::Storage(format!("write health observation: {e}")))?;
            info!("UPDATE_HEALTH_OBSERVATION_STARTED");
            return Ok(true);
        }

        let obs_bytes = std::fs::read(&obs_path)
            .map_err(|e| AppError::Storage(format!("read health observation: {e}")))?;
        let obs: HealthObservation = serde_json::from_slice(&obs_bytes)
            .map_err(|e| AppError::Storage(format!("parse health observation: {e}")))?;

        let started_at = obs
            .started_at
            .parse::<chrono::DateTime<chrono::Utc>>()
            .map_err(|e| AppError::Internal(format!("invalid observation time: {e}")))?;
        let elapsed = chrono::Utc::now().signed_duration_since(started_at);

        if elapsed.num_seconds() < 30 {
            info!(
                elapsed = %elapsed.num_seconds(),
                "UPDATE_HEALTH_OBSERVATION_IN_PROGRESS"
            );
            return Ok(true);
        }

        info!("UPDATE_HEALTH_OBSERVATION_PASSED");
        self.mark_stable(app_version)?;
        self.delete_pending_marker()?;
        self.delete_backup(&marker.backup_id)?;
        let _ = std::fs::remove_file(&obs_path);
        Ok(true)
    }

    pub fn delete_backup(&self, backup_id: &str) -> Result<(), AppError> {
        let backup_dir = self.backups_path().join(backup_id);
        if backup_dir.exists() {
            std::fs::remove_dir_all(&backup_dir)
                .map_err(|e| AppError::Storage(format!("delete backup: {e}")))?;
            info!(backup_id = %backup_id, "UPDATE_BACKUP_DELETED");
        }
        Ok(())
    }

    pub fn cleanup_staging(&self, staging_path: &Path) {
        if staging_path.exists() {
            if let Err(e) = std::fs::remove_file(staging_path) {
                warn!(error = %e, "UPDATE_CLEANUP_STAGING_FAILED");
            }
        }
    }
}
