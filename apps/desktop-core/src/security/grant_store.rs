use std::collections::HashMap;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use tokio::sync::RwLock;
use tracing::{info, warn};
use uuid::Uuid;

use crate::error::AppError;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub enum GrantKind {
    #[serde(rename = "workspace")]
    Workspace,
    #[serde(rename = "readonly_file")]
    ReadonlyFile,
}

#[derive(Debug, Clone)]
pub struct FileGrant {
    pub grant_id: Uuid,
    pub kind: GrantKind,
    pub canonical_path: PathBuf,
    pub device: u64,
    pub inode: u64,
    pub consumed: bool,
}

pub struct GrantStore {
    grants: RwLock<HashMap<Uuid, FileGrant>>,
    bookmarks: RwLock<HashMap<Uuid, PathBuf>>,
    profile_root: RwLock<Option<PathBuf>>,
}

impl GrantStore {
    pub fn new() -> Self {
        Self {
            grants: RwLock::new(HashMap::new()),
            bookmarks: RwLock::new(HashMap::new()),
            profile_root: RwLock::new(None),
        }
    }

    pub async fn create_grant(
        &self,
        selected_path: &Path,
        kind: GrantKind,
    ) -> Result<FileGrant, AppError> {
        let canonical = selected_path
            .canonicalize()
            .map_err(|error| AppError::Validation(format!("Cannot resolve path: {error}")))?;

        let metadata = std::fs::metadata(&canonical)
            .map_err(|error| AppError::Validation(format!("Cannot read path metadata: {error}")))?;

        #[cfg(unix)]
        use std::os::unix::fs::MetadataExt;
        let device = metadata.dev();
        let inode = metadata.ino();

        validate_path_safety(&canonical)?;

        let grant_id = Uuid::new_v4();
        let grant = FileGrant {
            grant_id,
            kind: kind.clone(),
            canonical_path: canonical,
            device,
            inode,
            consumed: false,
        };

        self.grants.write().await.insert(grant_id, grant.clone());
        if matches!(kind, GrantKind::Workspace) {
            // Workspace grants are also the security-scoped bookmark root used
            // by the one-shot external-write reverse RPC.  Keeping the same
            // UUID means the Sidecar never sends an untrusted filesystem root.
            self.bookmarks
                .write()
                .await
                .insert(grant_id, grant.canonical_path.clone());
        }
        info!(grant_id = %grant_id, kind = ?kind, "grant.created");
        Ok(grant)
    }

    pub async fn get_grant(&self, grant_id: Uuid) -> Result<FileGrant, AppError> {
        self.grants
            .read()
            .await
            .get(&grant_id)
            .cloned()
            .ok_or_else(|| {
                AppError::NotFound(format!("Grant {grant_id} does not exist or is stale"))
            })
    }

    pub async fn resolve_and_verify(&self, grant_id: Uuid) -> Result<PathBuf, AppError> {
        let grant = self.get_grant(grant_id).await?;
        let canonical = grant.canonical_path.canonicalize().map_err(|error| {
            AppError::Security(format!("Grant path is no longer accessible: {error}"))
        })?;
        let metadata = std::fs::metadata(&canonical).map_err(|error| {
            AppError::Security(format!("Grant metadata is unavailable: {error}"))
        })?;
        #[cfg(unix)]
        use std::os::unix::fs::MetadataExt;
        if metadata.dev() != grant.device || metadata.ino() != grant.inode {
            return Err(AppError::Security(format!(
                "Grant {grant_id} points to a different file (stale)"
            )));
        }
        Ok(canonical)
    }

    pub async fn resolve_workspace_grant(&self, grant_id: Uuid) -> Result<PathBuf, AppError> {
        let grant = self.get_grant(grant_id).await?;
        if grant.kind != GrantKind::Workspace {
            return Err(AppError::Security("WORKSPACE_GRANT_REQUIRED".to_owned()));
        }
        let canonical = grant.canonical_path.canonicalize().map_err(|error| {
            AppError::Security(format!("Grant path is no longer accessible: {error}"))
        })?;
        let metadata = std::fs::metadata(&canonical).map_err(|error| {
            AppError::Security(format!("Grant metadata is unavailable: {error}"))
        })?;
        #[cfg(unix)]
        use std::os::unix::fs::MetadataExt;
        if metadata.dev() != grant.device || metadata.ino() != grant.inode {
            return Err(AppError::Security("WORKSPACE_GRANT_STALE".to_owned()));
        }
        Ok(canonical)
    }

    pub async fn bind_profile_root(&self, root: Option<PathBuf>) -> Result<(), AppError> {
        let canonical = match root {
            Some(path) => {
                let canonical = path
                    .canonicalize()
                    .map_err(|error| AppError::Storage(error.to_string()))?;
                validate_path_safety(&canonical)?;
                Some(canonical)
            }
            None => None,
        };
        *self.profile_root.write().await = canonical;
        Ok(())
    }

    pub async fn profile_root(&self) -> Result<PathBuf, AppError> {
        self.profile_root
            .read()
            .await
            .clone()
            .ok_or_else(|| AppError::Security("PROFILE_NOT_OPEN".to_owned()))
    }

    pub async fn consume_grant(&self, grant_id: Uuid) -> Result<PathBuf, AppError> {
        let mut grants = self.grants.write().await;
        let grant = grants
            .get_mut(&grant_id)
            .ok_or_else(|| AppError::NotFound(format!("Grant {grant_id} not found")))?;
        if grant.consumed {
            return Err(AppError::Security(format!(
                "Grant {grant_id} has already been consumed"
            )));
        }
        grant.consumed = true;
        Ok(grant.canonical_path.clone())
    }

    pub async fn remove_grant(&self, grant_id: &Uuid) {
        self.grants.write().await.remove(grant_id);
        self.bookmarks.write().await.remove(grant_id);
        info!(grant_id = %grant_id, "grant.removed");
    }

    pub async fn clear(&self) {
        self.grants.write().await.clear();
        self.bookmarks.write().await.clear();
        *self.profile_root.write().await = None;
        warn!("grants.all_cleared");
    }

    // -- Bookmark methods (Security Scoped Bookmarks for external writes) --

    pub async fn store_bookmark(&self, bookmark_id: Uuid, path: &Path) -> Result<(), AppError> {
        let canonical = path
            .canonicalize()
            .map_err(|e| AppError::Validation(format!("Cannot resolve bookmark path: {e}")))?;
        self.bookmarks.write().await.insert(bookmark_id, canonical);
        info!(bookmark_id = %bookmark_id, "bookmark.stored");
        Ok(())
    }

    pub async fn resolve_bookmark(&self, bookmark_id: Uuid) -> Result<PathBuf, AppError> {
        let guard = self.bookmarks.read().await;
        guard
            .get(&bookmark_id)
            .cloned()
            .ok_or_else(|| AppError::NotFound(format!("Bookmark {bookmark_id} not found")))
    }

    pub async fn remove_bookmark(&self, bookmark_id: Uuid) -> Result<(), AppError> {
        self.bookmarks.write().await.remove(&bookmark_id);
        info!(bookmark_id = %bookmark_id, "bookmark.removed");
        Ok(())
    }
}

fn validate_path_safety(path: &Path) -> Result<(), AppError> {
    let path_str = path.to_string_lossy();

    #[cfg(target_os = "macos")]
    let protected_dirs = [
        "/private/etc",
        "/private/tmp",
        "/private/var/db",
        "/private/var/root",
        "/Library/Keychains",
        "/System",
        "/dev",
        "/cores",
    ];
    #[cfg(not(target_os = "macos"))]
    let protected_dirs = ["/etc", "/var", "/tmp", "/root", "/sys", "/proc", "/dev"];

    for dir in &protected_dirs {
        if path_str == *dir || path_str.starts_with(&format!("{dir}/")) {
            return Err(AppError::Security(format!(
                "Protected system path not allowed: {dir}"
            )));
        }
    }

    let home = dirs::home_dir().map(|h| h.to_string_lossy().to_string());
    if let Some(ref home) = home {
        let protected_home = [
            "/.ssh",
            "/.gnupg",
            "/.aws",
            "/.kube",
            "/Library/Keychains",
            "/.config",
            "/.local/share/keyrings",
        ];
        for suffix in &protected_home {
            let full = format!("{home}{suffix}");
            if path_str == full || path_str.starts_with(&format!("{full}/")) {
                return Err(AppError::Security(format!(
                    "Protected home path not allowed: {suffix}"
                )));
            }
        }
    }

    let ibreeze_data = dirs::data_local_dir()
        .map(|d| d.join("ibreeze"))
        .unwrap_or_default();
    if !ibreeze_data.as_os_str().is_empty() && path.starts_with(&ibreeze_data) {
        return Err(AppError::Security(
            "iBreeze data directory is not accessible".to_owned(),
        ));
    }

    Ok(())
}

impl Default for GrantStore {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    #[tokio::test]
    async fn grant_creation_and_verification() {
        let store = GrantStore::new();
        let dir = TempDir::new_in(".").expect("temp dir");
        let grant = store
            .create_grant(dir.path(), GrantKind::Workspace)
            .await
            .expect("create grant");
        assert_eq!(grant.kind, GrantKind::Workspace);
        let resolved = store
            .resolve_and_verify(grant.grant_id)
            .await
            .expect("resolve");
        assert_eq!(resolved, dir.path().canonicalize().unwrap());
    }

    #[tokio::test]
    async fn grant_consumption_is_one_shot() {
        let store = GrantStore::new();
        let dir = TempDir::new_in(".").expect("temp dir");
        let grant = store
            .create_grant(dir.path(), GrantKind::ReadonlyFile)
            .await
            .expect("create grant");
        store
            .consume_grant(grant.grant_id)
            .await
            .expect("first consume");
        assert!(store.consume_grant(grant.grant_id).await.is_err());
    }

    #[tokio::test]
    async fn protected_paths_are_rejected() {
        let store = GrantStore::new();
        let candidate = PathBuf::from("/etc/passwd");
        assert!(store
            .create_grant(&candidate, GrantKind::ReadonlyFile)
            .await
            .is_err());
    }

    #[tokio::test]
    async fn stale_grant_is_rejected() {
        let store = GrantStore::new();
        let dir = TempDir::new_in(".").expect("temp dir");
        let grant = store
            .create_grant(dir.path(), GrantKind::Workspace)
            .await
            .expect("create grant");
        std::fs::remove_dir_all(dir.path()).expect("remove dir");
        assert!(store.resolve_and_verify(grant.grant_id).await.is_err());
    }
}
