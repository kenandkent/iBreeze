use std::collections::HashMap;
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};

use sha2::{Digest, Sha256};
use tokio::sync::RwLock;
use tracing::info;
use uuid::Uuid;

use crate::error::AppError;
use crate::rpc::reverse::{ExternalWriteOperation, ExternalWriteRequest, ExternalWriteResponse};
use crate::security::grant_store::GrantStore;

#[derive(Debug, Clone)]
pub struct Receipt {
    pub receipt_sha256: String,
    pub request_hash: String,
    pub old_state_sha256: String,
    pub new_state_sha256: String,
    pub executed_at: String,
}

pub struct ReceiptStore {
    by_request_hash: RwLock<HashMap<String, Receipt>>,
}

impl ReceiptStore {
    pub fn new() -> Self {
        Self {
            by_request_hash: RwLock::new(HashMap::new()),
        }
    }

    pub async fn get_by_request_hash(&self, request_hash: &str) -> Option<Receipt> {
        self.by_request_hash.read().await.get(request_hash).cloned()
    }

    pub async fn insert(&self, receipt: Receipt) {
        let hash = receipt.request_hash.clone();
        self.by_request_hash.write().await.insert(hash, receipt);
    }
}

impl Default for ReceiptStore {
    fn default() -> Self {
        Self::new()
    }
}

fn compute_sha256(path: &Path) -> Result<String, AppError> {
    let data =
        fs::read(path).map_err(|e| AppError::Io(format!("Cannot read {}: {e}", path.display())))?;
    let mut hasher = Sha256::new();
    hasher.update(&data);
    Ok(format!("{:x}", hasher.finalize()))
}

fn file_exists(path: &Path) -> bool {
    fs::metadata(path).is_ok()
}

fn compute_target_state_sha256(
    target: &Path,
    op: &ExternalWriteOperation,
) -> Result<String, AppError> {
    match op {
        ExternalWriteOperation::CreateFile | ExternalWriteOperation::ReplaceFile => {
            if file_exists(target) {
                compute_sha256(target)
            } else {
                Ok(String::new())
            }
        }
        ExternalWriteOperation::DeleteFile | ExternalWriteOperation::CreateDirectory => {
            Ok(String::new())
        }
    }
}

fn generate_request_hash(
    approval_id: Uuid,
    run_id: Uuid,
    operation: &ExternalWriteOperation,
    target: &str,
) -> String {
    let op_str = match operation {
        ExternalWriteOperation::CreateFile => "create_file",
        ExternalWriteOperation::ReplaceFile => "replace_file",
        ExternalWriteOperation::DeleteFile => "delete_file",
        ExternalWriteOperation::CreateDirectory => "create_directory",
    };
    let input = format!("{approval_id}{run_id}{op_str}{target}");
    let mut hasher = Sha256::new();
    hasher.update(input.as_bytes());
    format!("{:x}", hasher.finalize())
}

fn generate_receipt_sha256(
    approval_id: Uuid,
    run_id: Uuid,
    operation: &ExternalWriteOperation,
    target: &str,
    old_sha: &str,
    new_sha: &str,
) -> String {
    let op_str = match operation {
        ExternalWriteOperation::CreateFile => "create_file",
        ExternalWriteOperation::ReplaceFile => "replace_file",
        ExternalWriteOperation::DeleteFile => "delete_file",
        ExternalWriteOperation::CreateDirectory => "create_directory",
    };
    let input = format!("{approval_id}{run_id}{op_str}{target}{old_sha}{new_sha}");
    let mut hasher = Sha256::new();
    hasher.update(input.as_bytes());
    format!("{:x}", hasher.finalize())
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

    let mut file = fs::File::create(&tmp_path)
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

fn validate_target_within_bookmark(target: &Path, bookmarked_path: &Path) -> Result<(), AppError> {
    let bookmark_canonical = bookmarked_path
        .canonicalize()
        .map_err(|_| AppError::Security("Bookmarked path does not exist".to_owned()))?;

    let target_canonical = if target.exists() {
        target
            .canonicalize()
            .map_err(|_| AppError::Security("Target path is inaccessible".to_owned()))?
    } else if let Some(parent) = target.parent() {
        let parent_canonical = parent.canonicalize().map_err(|_| {
            AppError::Security("Target parent directory is inaccessible".to_owned())
        })?;
        let name = target
            .file_name()
            .ok_or_else(|| AppError::Security("Target must have a filename".to_owned()))?;
        parent_canonical.join(name)
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
    Ok(())
}

pub async fn handle_external_write_execute(
    request: ExternalWriteRequest,
    grant_store: &GrantStore,
    receipt_store: &ReceiptStore,
) -> Result<ExternalWriteResponse, AppError> {
    if is_expired(&request.expires_at) {
        return Err(AppError::Security("APPROVAL_EXPIRED".to_owned()));
    }

    if request.run_id.is_nil() {
        return Err(AppError::Validation("run_id cannot be nil".to_owned()));
    }

    let target = PathBuf::from(&request.target_realpath);

    if let Ok(bookmarked_path) = grant_store.resolve_bookmark(request.approval_id).await {
        validate_target_within_bookmark(&target, &bookmarked_path)?;
    }

    let old_sha = if file_exists(&target) {
        compute_sha256(&target)?
    } else {
        String::new()
    };

    let request_hash = generate_request_hash(
        request.approval_id,
        request.run_id,
        &request.operation,
        &request.target_realpath,
    );

    if let Some(receipt) = receipt_store.get_by_request_hash(&request_hash).await {
        let current_sha = compute_target_state_sha256(&target, &request.operation)?;
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
        } else {
            return Err(AppError::Security(
                "SECURITY_RISK: target state does not match receipt".to_owned(),
            ));
        }
    }

    if let Some(expected) = &request.expected_old_sha256 {
        if old_sha != *expected {
            return Err(AppError::Security("APPROVAL_TARGET_CHANGED".to_owned()));
        }
    }

    match &request.operation {
        ExternalWriteOperation::CreateFile => {
            let content = String::new();
            atomic_create(&target, content.as_bytes())?;
        }
        ExternalWriteOperation::ReplaceFile => {
            if !file_exists(&target) {
                return Err(AppError::Security(
                    "APPROVAL_TARGET_CHANGED: target does not exist for replace".to_owned(),
                ));
            }
            let content =
                fs::read(&target).map_err(|e| AppError::Io(format!("Cannot read target: {e}")))?;
            atomic_write(&target, &content)?;
        }
        ExternalWriteOperation::DeleteFile => {
            if !file_exists(&target) {
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

    let new_sha = compute_target_state_sha256(&target, &request.operation)?;

    let receipt_sha256 = generate_receipt_sha256(
        request.approval_id,
        request.run_id,
        &request.operation,
        &request.target_realpath,
        &old_sha,
        &new_sha,
    );

    let completed_at = now_iso();

    let receipt = Receipt {
        receipt_sha256: receipt_sha256.clone(),
        request_hash,
        old_state_sha256: old_sha,
        new_state_sha256: new_sha.clone(),
        executed_at: completed_at.clone(),
    };
    receipt_store.insert(receipt).await;
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
