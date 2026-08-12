use std::collections::HashMap;
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use tokio::sync::RwLock;
use tracing::info;
use uuid::Uuid;

use crate::error::AppError;
use crate::rpc::reverse::{ExternalWriteOperation, ExternalWriteRequest, ExternalWriteResponse};
use crate::security::grant_store::GrantStore;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Receipt {
    pub receipt_sha256: String,
    pub request_hash: String,
    pub old_state_sha256: String,
    pub new_state_sha256: String,
    pub executed_at: String,
}

pub struct ReceiptStore {
    by_request_hash: RwLock<HashMap<String, Receipt>>,
    profile_root: RwLock<Option<PathBuf>>,
}

impl ReceiptStore {
    pub fn new() -> Self {
        Self {
            by_request_hash: RwLock::new(HashMap::new()),
            profile_root: RwLock::new(None),
        }
    }

    pub async fn get_by_request_hash(&self, request_hash: &str) -> Option<Receipt> {
        self.by_request_hash.read().await.get(request_hash).cloned()
    }

    pub async fn bind_profile_root(&self, root: Option<PathBuf>) -> Result<(), AppError> {
        let loaded = if let Some(root) = root.as_ref() {
            let canonical = root
                .canonicalize()
                .map_err(|_| AppError::Security("PROFILE_RUNTIME_ROOT_INVALID".to_owned()))?;
            let path = canonical.join("external-write-receipts.v1.json");
            if path.exists() {
                let raw = fs::read_to_string(&path)
                    .map_err(|_| AppError::Storage("RECEIPT_STORE_READ_FAILED".to_owned()))?;
                serde_json::from_str::<HashMap<String, Receipt>>(&raw)
                    .map_err(|_| AppError::Storage("RECEIPT_STORE_INVALID".to_owned()))?
            } else {
                HashMap::new()
            }
        } else {
            HashMap::new()
        };
        *self.by_request_hash.write().await = loaded;
        *self.profile_root.write().await = root
            .map(|value| value.canonicalize())
            .transpose()
            .map_err(|_| AppError::Security("PROFILE_RUNTIME_ROOT_INVALID".to_owned()))?;
        Ok(())
    }

    pub async fn clear(&self) {
        self.by_request_hash.write().await.clear();
        *self.profile_root.write().await = None;
    }

    pub async fn insert(&self, receipt: Receipt) -> Result<(), AppError> {
        let hash = receipt.request_hash.clone();
        let snapshot = {
            let mut guard = self.by_request_hash.write().await;
            guard.insert(hash.clone(), receipt);
            guard.clone()
        };
        if let Some(root) = self.profile_root.read().await.clone() {
            if let Err(error) = persist_receipts(&root, &snapshot) {
                self.by_request_hash.write().await.remove(&hash);
                return Err(error);
            }
        }
        Ok(())
    }
}

fn persist_receipts(root: &Path, receipts: &HashMap<String, Receipt>) -> Result<(), AppError> {
    let path = root.join("external-write-receipts.v1.json");
    let temp = root.join(format!(".external-write-receipts.{}.tmp", Uuid::new_v4()));
    let encoded = serde_json::to_vec(receipts)
        .map_err(|_| AppError::Storage("RECEIPT_STORE_SERIALIZE_FAILED".to_owned()))?;
    let mut options = fs::OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut file = options
        .open(&temp)
        .map_err(|_| AppError::Storage("RECEIPT_STORE_WRITE_FAILED".to_owned()))?;
    file.write_all(&encoded)
        .map_err(|_| AppError::Storage("RECEIPT_STORE_WRITE_FAILED".to_owned()))?;
    file.sync_all()
        .map_err(|_| AppError::Storage("RECEIPT_STORE_FSYNC_FAILED".to_owned()))?;
    fs::rename(&temp, &path)
        .map_err(|_| AppError::Storage("RECEIPT_STORE_RENAME_FAILED".to_owned()))?;
    if let Ok(directory) = fs::File::open(root) {
        let _ = directory.sync_all();
    }
    Ok(())
}

impl Default for ReceiptStore {
    fn default() -> Self {
        Self::new()
    }
}

fn reject_symlink(path: &Path, code: &str) -> Result<(), AppError> {
    if let Ok(metadata) = fs::symlink_metadata(path) {
        if metadata.file_type().is_symlink() {
            return Err(AppError::Security(code.to_owned()));
        }
    } else if path.exists() {
        return Err(AppError::Security(code.to_owned()));
    }
    Ok(())
}

fn operation_name(operation: &ExternalWriteOperation) -> &'static str {
    match operation {
        ExternalWriteOperation::CreateFile => "create_file",
        ExternalWriteOperation::ReplaceFile => "replace_file",
        ExternalWriteOperation::DeleteFile => "delete_file",
        ExternalWriteOperation::CreateDirectory => "create_directory",
    }
}

fn compute_target_state_sha256(target: &Path) -> Result<String, AppError> {
    let (exists, kind, size, content_sha256) = match fs::symlink_metadata(target) {
        Ok(metadata) if metadata.file_type().is_symlink() => {
            return Err(AppError::Security("TARGET_SYMLINK_NOT_ALLOWED".to_owned()));
        }
        Ok(metadata) if metadata.is_file() => {
            let data = fs::read(target)
                .map_err(|e| AppError::Io(format!("Cannot read {}: {e}", target.display())))?;
            (
                true,
                "file",
                data.len() as u64,
                format!("{:x}", Sha256::digest(&data)),
            )
        }
        Ok(metadata) if metadata.is_dir() => (true, "directory", 0, String::new()),
        Ok(_) => {
            return Err(AppError::Security("TARGET_TYPE_NOT_SUPPORTED".to_owned()));
        }
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            (false, "missing", 0, String::new())
        }
        Err(error) => return Err(AppError::Io(format!("Cannot inspect target: {error}"))),
    };

    let mut state = std::collections::BTreeMap::new();
    state.insert("content_sha256", Value::String(content_sha256));
    state.insert("exists", Value::Bool(exists));
    state.insert("kind", Value::String(kind.to_owned()));
    state.insert("size", Value::from(size));
    let encoded = serde_json::to_vec(&state).map_err(|e| AppError::Internal(e.to_string()))?;
    Ok(format!("{:x}", Sha256::digest(encoded)))
}

#[allow(clippy::too_many_arguments)]
fn generate_request_hash(
    approval_id: Uuid,
    workspace_grant_id: Uuid,
    run_id: Uuid,
    operation: &ExternalWriteOperation,
    target: &str,
    expected_old_sha256: Option<&str>,
    source_relative_path: Option<&str>,
    source_sha256: Option<&str>,
    source_size: Option<u64>,
) -> String {
    let op_str = operation_name(operation);
    let input = serde_json::json!({
        "approval_id": approval_id,
        "workspace_grant_id": workspace_grant_id,
        "run_id": run_id,
        "operation": op_str,
        "target_realpath": target,
        "expected_old_sha256": expected_old_sha256,
        "source_relative_path": source_relative_path,
        "source_sha256": source_sha256,
        "source_size": source_size,
    });
    let mut hasher = Sha256::new();
    hasher.update(serde_json::to_vec(&input).unwrap_or_default());
    format!("{:x}", hasher.finalize())
}

fn generate_receipt_sha256(
    approval_id: Uuid,
    run_id: Uuid,
    operation: &ExternalWriteOperation,
    target: &str,
    new_sha: &str,
    completed_at: &str,
) -> String {
    let mut response = std::collections::BTreeMap::new();
    response.insert("approval_id", Value::String(approval_id.to_string()));
    response.insert("completed_at", Value::String(completed_at.to_owned()));
    response.insert(
        "operation",
        Value::String(operation_name(operation).to_owned()),
    );
    response.insert("result_state_sha256", Value::String(new_sha.to_owned()));
    response.insert("run_id", Value::String(run_id.to_string()));
    response.insert("target_realpath", Value::String(target.to_owned()));
    let encoded = serde_json::to_vec(&response).unwrap_or_default();
    format!("{:x}", Sha256::digest(encoded))
}

fn now_iso() -> String {
    chrono::Utc::now()
        .format("%Y-%m-%dT%H:%M:%S%.fZ")
        .to_string()
}

fn is_expired(expires_at: &str) -> bool {
    if let Ok(expires) = chrono::DateTime::parse_from_rfc3339(expires_at) {
        chrono::Utc::now() > expires
    } else {
        true
    }
}

fn atomic_write(target: &Path, content: &[u8]) -> Result<(), AppError> {
    let dir = target
        .parent()
        .ok_or_else(|| AppError::Validation("No parent directory".to_owned()))?;
    let tmp_name = format!(".ibreeze_tmp_{}", Uuid::new_v4());
    let tmp_path = dir.join(&tmp_name);

    let mut options = fs::OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut file = options
        .open(&tmp_path)
        .map_err(|e| AppError::Io(format!("Cannot create temp file: {e}")))?;
    file.write_all(content)
        .map_err(|e| AppError::Io(format!("Cannot write temp file: {e}")))?;
    file.sync_all()
        .map_err(|e| AppError::Io(format!("Cannot fsync temp file: {e}")))?;

    fs::rename(&tmp_path, target)
        .map_err(|e| AppError::Io(format!("Cannot rename temp to target: {e}")))?;

    let dir_file =
        fs::File::open(dir).map_err(|e| AppError::Io(format!("Cannot open dir for fsync: {e}")))?;
    dir_file
        .sync_all()
        .map_err(|e| AppError::Io(format!("Cannot fsync directory: {e}")))?;

    Ok(())
}

fn atomic_create(target: &Path, content: &[u8]) -> Result<(), AppError> {
    if target.exists() || fs::symlink_metadata(target).is_ok() {
        return Err(AppError::Security("APPROVAL_TARGET_CHANGED".to_owned()));
    }
    if let Some(parent) = target.parent() {
        fs::create_dir_all(parent)
            .map_err(|e| AppError::Io(format!("Cannot create parent dirs: {e}")))?;
    }
    atomic_write(target, content)
}

fn atomic_delete(target: &Path) -> Result<(), AppError> {
    fs::remove_file(target).map_err(|e| AppError::Io(format!("Cannot delete file: {e}")))?;

    if let Some(parent) = target.parent() {
        let dir_file = fs::File::open(parent)
            .map_err(|e| AppError::Io(format!("Cannot open dir for fsync: {e}")))?;
        dir_file
            .sync_all()
            .map_err(|e| AppError::Io(format!("Cannot fsync directory: {e}")))?;
    }

    Ok(())
}

fn reject_symlink_components(path: &Path, root: &Path) -> Result<(), AppError> {
    // The user-facing path can contain an OS-level alias for the canonical
    // root (for example macOS `/var` -> `/private/var`).  Do not reject that
    // alias merely because it is not lexically prefixed by the canonical
    // path.  A symlink is allowed only when it is an ancestor alias needed to
    // reach `root`; a symlink at or below the root is always rejected.
    let mut current = PathBuf::new();
    for component in path.components() {
        if matches!(component, std::path::Component::ParentDir) {
            return Err(AppError::Security("Target path is invalid".to_owned()));
        }
        current.push(component.as_os_str());
        if let Ok(metadata) = fs::symlink_metadata(&current) {
            if metadata.file_type().is_symlink() {
                let resolved = current
                    .canonicalize()
                    .map_err(|_| AppError::Security("TARGET_SYMLINK_NOT_ALLOWED".to_owned()))?;
                let is_root_alias = root.starts_with(&resolved) && !resolved.starts_with(root);
                if !is_root_alias {
                    return Err(AppError::Security("TARGET_SYMLINK_NOT_ALLOWED".to_owned()));
                }
            }
        }
    }
    Ok(())
}

fn validate_target_within_bookmark(target: &Path, bookmarked_path: &Path) -> Result<(), AppError> {
    let bookmark_canonical = bookmarked_path
        .canonicalize()
        .map_err(|_| AppError::Security("Bookmarked path does not exist".to_owned()))?;

    if !target.is_absolute() {
        return Err(AppError::Validation(
            "target_realpath must be absolute".to_owned(),
        ));
    }
    // Check the user-supplied lexical path before canonicalization.  Checking
    // only the canonical result would turn an in-workspace symlink alias into
    // an apparently safe ordinary path and would make the no-symlink contract
    // dependent on where the alias happens to point today.
    reject_symlink_components(target, &bookmark_canonical)?;
    reject_symlink(target, "TARGET_SYMLINK_NOT_ALLOWED")?;
    let target_canonical = if target.exists() {
        target
            .canonicalize()
            .map_err(|_| AppError::Security("Target path is inaccessible".to_owned()))?
    } else if let Some(parent) = target.parent() {
        let mut existing = parent.to_path_buf();
        while !existing.exists() {
            existing = existing
                .parent()
                .ok_or_else(|| {
                    AppError::Security("Target parent directory is inaccessible".to_owned())
                })?
                .to_path_buf();
        }
        let parent_canonical = existing.canonicalize().map_err(|_| {
            AppError::Security("Target parent directory is inaccessible".to_owned())
        })?;
        if !parent_canonical.starts_with(&bookmark_canonical) {
            return Err(AppError::Security(
                "Target parent is outside bookmarked path".to_owned(),
            ));
        }
        let relative_missing = parent
            .strip_prefix(&existing)
            .map_err(|_| AppError::Security("Target path is invalid".to_owned()))?;
        if relative_missing.components().any(|component| {
            matches!(
                component,
                std::path::Component::ParentDir | std::path::Component::RootDir
            )
        }) {
            return Err(AppError::Security("Target path is invalid".to_owned()));
        }
        let name = target
            .file_name()
            .ok_or_else(|| AppError::Security("Target must have a filename".to_owned()))?;
        parent_canonical.join(relative_missing).join(name)
    } else {
        return Err(AppError::Security("Target path is invalid".to_owned()));
    };

    if !target_canonical.starts_with(&bookmark_canonical) {
        return Err(AppError::Security(format!(
            "Path traversal: target {} is outside bookmarked path {}",
            target_canonical.display(),
            bookmark_canonical.display(),
        )));
    }
    reject_symlink_components(&target_canonical, &bookmark_canonical)?;
    Ok(())
}

fn load_source(
    staging_root: &Path,
    relative_path: &str,
    expected_sha256: &str,
    expected_size: u64,
) -> Result<Vec<u8>, AppError> {
    let relative = Path::new(relative_path);
    if relative.is_absolute()
        || relative.components().any(|component| {
            matches!(
                component,
                std::path::Component::ParentDir | std::path::Component::RootDir
            )
        })
    {
        return Err(AppError::Security("SOURCE_PATH_INVALID".to_owned()));
    }
    let staging_canonical = staging_root
        .canonicalize()
        .map_err(|_| AppError::Security("SOURCE_STAGING_NOT_FOUND".to_owned()))?;
    let source = staging_canonical.join(relative);
    reject_symlink_components(&source, &staging_canonical)
        .map_err(|_| AppError::Security("SOURCE_SYMLINK_NOT_ALLOWED".to_owned()))?;
    reject_symlink(&source, "SOURCE_SYMLINK_NOT_ALLOWED")?;
    let canonical = source
        .canonicalize()
        .map_err(|_| AppError::Security("SOURCE_NOT_FOUND".to_owned()))?;
    if !canonical.starts_with(&staging_canonical) {
        return Err(AppError::Security("SOURCE_OUTSIDE_STAGING".to_owned()));
    }
    let metadata =
        fs::metadata(&canonical).map_err(|_| AppError::Security("SOURCE_NOT_FOUND".to_owned()))?;
    if !metadata.is_file() || metadata.len() != expected_size {
        return Err(AppError::Security("SOURCE_METADATA_MISMATCH".to_owned()));
    }
    let content =
        fs::read(&canonical).map_err(|_| AppError::Security("SOURCE_NOT_FOUND".to_owned()))?;
    let actual = format!("{:x}", Sha256::digest(&content));
    if actual != expected_sha256 {
        return Err(AppError::Security("SOURCE_HASH_MISMATCH".to_owned()));
    }
    Ok(content)
}

pub async fn handle_external_write_execute(
    request: ExternalWriteRequest,
    grant_store: &GrantStore,
    receipt_store: &ReceiptStore,
) -> Result<ExternalWriteResponse, AppError> {
    if request.run_id.is_nil() {
        return Err(AppError::Validation("run_id cannot be nil".to_owned()));
    }

    let target = PathBuf::from(&request.target_realpath);
    let bookmarked_path = grant_store
        .resolve_workspace_grant(request.workspace_grant_id)
        .await
        .map_err(|_| AppError::Security("WORKSPACE_GRANT_REQUIRED".to_owned()))?;
    validate_target_within_bookmark(&target, &bookmarked_path)?;

    let request_hash = generate_request_hash(
        request.approval_id,
        request.workspace_grant_id,
        request.run_id,
        &request.operation,
        &request.target_realpath,
        request.expected_old_sha256.as_deref(),
        request.source_relative_path.as_deref(),
        request.source_sha256.as_deref(),
        request.source_size,
    );

    // A lost response may be retried after the approval TTL. If the target
    // already equals the recorded result, reconstruct the receipt without
    // reading staging or creating another side effect.
    if let Some(receipt) = receipt_store.get_by_request_hash(&request_hash).await {
        let current_sha = compute_target_state_sha256(&target)?;
        if current_sha == receipt.new_state_sha256 {
            return Ok(ExternalWriteResponse {
                approval_id: request.approval_id,
                run_id: request.run_id,
                operation: request.operation,
                target_realpath: request.target_realpath,
                result_state_sha256: receipt.new_state_sha256,
                completed_at: receipt.executed_at,
                receipt_sha256: receipt.receipt_sha256,
            });
        }
        return Err(AppError::Security(
            "SECURITY_RISK: target state does not match receipt".to_owned(),
        ));
    }

    if is_expired(&request.expires_at) {
        return Err(AppError::Security("APPROVAL_EXPIRED".to_owned()));
    }

    let source = match &request.operation {
        ExternalWriteOperation::CreateFile | ExternalWriteOperation::ReplaceFile => {
            let relative = request
                .source_relative_path
                .as_deref()
                .ok_or_else(|| AppError::Validation("SOURCE_REQUIRED".to_owned()))?;
            let sha = request
                .source_sha256
                .as_deref()
                .ok_or_else(|| AppError::Validation("SOURCE_REQUIRED".to_owned()))?;
            let size = request
                .source_size
                .ok_or_else(|| AppError::Validation("SOURCE_REQUIRED".to_owned()))?;
            let profile_root = grant_store.profile_root().await?;
            let staging_root = profile_root
                .join("external-write-staging")
                .join(request.approval_id.to_string());
            Some(load_source(&staging_root, relative, sha, size)?)
        }
        _ => {
            if request.source_relative_path.is_some()
                || request.source_sha256.is_some()
                || request.source_size.is_some()
            {
                return Err(AppError::Validation("SOURCE_NOT_ALLOWED".to_owned()));
            }
            None
        }
    };

    let old_sha = compute_target_state_sha256(&target)?;

    if let Some(expected) = &request.expected_old_sha256 {
        if old_sha != *expected {
            return Err(AppError::Security("APPROVAL_TARGET_CHANGED".to_owned()));
        }
    }

    match &request.operation {
        ExternalWriteOperation::CreateFile => {
            atomic_create(&target, source.as_deref().unwrap_or_default())?;
        }
        ExternalWriteOperation::ReplaceFile => {
            if !fs::metadata(&target)
                .map(|metadata| metadata.is_file())
                .unwrap_or(false)
            {
                return Err(AppError::Security(
                    "APPROVAL_TARGET_CHANGED: target does not exist for replace".to_owned(),
                ));
            }
            atomic_write(&target, source.as_deref().unwrap_or_default())?;
        }
        ExternalWriteOperation::DeleteFile => {
            if !fs::metadata(&target)
                .map(|metadata| metadata.is_file())
                .unwrap_or(false)
            {
                return Err(AppError::Security(
                    "APPROVAL_TARGET_CHANGED: target does not exist for delete".to_owned(),
                ));
            }
            atomic_delete(&target)?;
        }
        ExternalWriteOperation::CreateDirectory => {
            fs::create_dir_all(&target)
                .map_err(|e| AppError::Io(format!("Cannot create directory: {e}")))?;
        }
    }

    let new_sha = compute_target_state_sha256(&target)?;

    let completed_at = now_iso();

    let receipt_sha256 = generate_receipt_sha256(
        request.approval_id,
        request.run_id,
        &request.operation,
        &request.target_realpath,
        &new_sha,
        &completed_at,
    );

    let receipt = Receipt {
        receipt_sha256: receipt_sha256.clone(),
        request_hash,
        old_state_sha256: old_sha,
        new_state_sha256: new_sha.clone(),
        executed_at: completed_at.clone(),
    };
    receipt_store.insert(receipt).await?;
    if let Ok(profile_root) = grant_store.profile_root().await {
        let staging_root = profile_root
            .join("external-write-staging")
            .join(request.approval_id.to_string());
        let _ = fs::remove_dir_all(staging_root);
    }
    info!(%receipt_sha256, operation = ?request.operation, "external_write.executed");

    Ok(ExternalWriteResponse {
        approval_id: request.approval_id,
        run_id: request.run_id,
        operation: request.operation,
        target_realpath: request.target_realpath,
        result_state_sha256: new_sha,
        completed_at,
        receipt_sha256,
    })
}
