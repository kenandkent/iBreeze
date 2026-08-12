use std::fs;
use std::path::PathBuf;

use tempfile::TempDir;
use uuid::Uuid;

use ibreeze_desktop_core::rpc::reverse::{ExternalWriteOperation, ExternalWriteRequest};
use ibreeze_desktop_core::security::external_write::{handle_external_write_execute, ReceiptStore};
use ibreeze_desktop_core::security::grant_store::GrantStore;

fn make_request(
    operation: ExternalWriteOperation,
    target_realpath: String,
    expected_old_sha256: Option<String>,
) -> ExternalWriteRequest {
    ExternalWriteRequest {
        approval_id: Uuid::new_v4(),
        workspace_grant_id: Uuid::new_v4(),
        run_id: Uuid::new_v4(),
        operation,
        target_realpath,
        expected_old_sha256,
        source_relative_path: None,
        source_sha256: None,
        source_size: None,
        expires_at: "2099-12-31T23:59:59Z".to_owned(),
    }
}

async fn configure_request(
    request: &mut ExternalWriteRequest,
    workspace_root: &std::path::Path,
    grant_store: &GrantStore,
    source: Option<&[u8]>,
) {
    let grant = grant_store
        .create_grant(
            workspace_root,
            ibreeze_desktop_core::security::grant_store::GrantKind::Workspace,
        )
        .await
        .expect("workspace grant");
    request.workspace_grant_id = grant.grant_id;

    let profile_root = workspace_root.join("profile");
    fs::create_dir_all(&profile_root).expect("profile root");
    grant_store
        .bind_profile_root(Some(profile_root.clone()))
        .await
        .expect("bind profile root");
    if let Some(contents) = source {
        let staging = profile_root
            .join("external-write-staging")
            .join(request.approval_id.to_string());
        fs::create_dir_all(&staging).expect("staging root");
        let source_path = staging.join("content");
        fs::write(&source_path, contents).expect("staging content");
        use sha2::Digest;
        request.source_relative_path = Some("content".to_owned());
        request.source_sha256 = Some(format!("{:x}", sha2::Sha256::digest(contents)));
        request.source_size = Some(contents.len() as u64);
    }
}

fn state_sha_of(path: &PathBuf) -> String {
    use sha2::Digest;
    let data = fs::read(path).expect("read file");
    let mut state = std::collections::BTreeMap::new();
    state.insert(
        "content_sha256",
        serde_json::Value::String(format!("{:x}", sha2::Sha256::digest(&data))),
    );
    state.insert("exists", serde_json::Value::Bool(true));
    state.insert("kind", serde_json::Value::String("file".to_owned()));
    state.insert("size", serde_json::Value::from(data.len() as u64));
    format!(
        "{:x}",
        sha2::Sha256::digest(serde_json::to_vec(&state).expect("state json"))
    )
}

#[tokio::test]
async fn happy_path_create_file() {
    let dir = TempDir::new().expect("temp dir");
    let target = dir.path().join("new_file.txt");

    let grant_store = GrantStore::new();
    let receipt_store = ReceiptStore::new();

    let mut request = make_request(
        ExternalWriteOperation::CreateFile,
        target.to_string_lossy().to_string(),
        None,
    );
    configure_request(
        &mut request,
        dir.path(),
        &grant_store,
        Some(b"created content"),
    )
    .await;

    let response = handle_external_write_execute(request, &grant_store, &receipt_store)
        .await
        .expect("create file");

    assert!(target.exists(), "file should be created");
    assert_eq!(response.operation, ExternalWriteOperation::CreateFile);
    assert!(!response.receipt_sha256.is_empty());
    assert!(!response.result_state_sha256.is_empty());
}

#[tokio::test]
async fn happy_path_replace_file() {
    let dir = TempDir::new().expect("temp dir");
    let target = dir.path().join("existing.txt");
    fs::write(&target, b"original content").expect("write original");

    let grant_store = GrantStore::new();
    let receipt_store = ReceiptStore::new();
    let old_sha = state_sha_of(&target);

    let mut request = make_request(
        ExternalWriteOperation::ReplaceFile,
        target.to_string_lossy().to_string(),
        Some(old_sha),
    );
    configure_request(
        &mut request,
        dir.path(),
        &grant_store,
        Some(b"replacement content"),
    )
    .await;

    let response = handle_external_write_execute(request, &grant_store, &receipt_store)
        .await
        .expect("replace file");

    assert!(target.exists(), "file should exist after replace");
    assert_eq!(response.operation, ExternalWriteOperation::ReplaceFile);
    assert!(!response.receipt_sha256.is_empty());
}

#[tokio::test]
async fn path_traversal_is_rejected() {
    let dir = TempDir::new().expect("temp dir");
    let bookmark_path = dir.path().join("allowed");
    fs::create_dir(&bookmark_path).expect("create allowed dir");

    let grant_store = GrantStore::new();
    let grant = grant_store
        .create_grant(
            &bookmark_path,
            ibreeze_desktop_core::security::grant_store::GrantKind::Workspace,
        )
        .await
        .expect("workspace grant");

    let traversal_target = dir.path().join("secret.txt");
    // This target should be rejected since it's outside the bookmarked "allowed" dir

    let receipt_store = ReceiptStore::new();
    let request = ExternalWriteRequest {
        approval_id: Uuid::new_v4(),
        workspace_grant_id: grant.grant_id,
        run_id: Uuid::new_v4(),
        operation: ExternalWriteOperation::CreateFile,
        target_realpath: traversal_target.to_string_lossy().to_string(),
        expected_old_sha256: None,
        source_relative_path: None,
        source_sha256: None,
        source_size: None,
        expires_at: "2099-12-31T23:59:59Z".to_owned(),
    };

    let result = handle_external_write_execute(request, &grant_store, &receipt_store).await;
    assert!(result.is_err(), "path traversal should be rejected");
    let err = result.unwrap_err();
    let err_msg = err.to_string();
    assert!(
        err_msg.contains("Path traversal")
            || err_msg.contains("outside bookmarked path")
            || err_msg.contains("SECURITY_ERROR"),
        "unexpected error: {err_msg}"
    );
}

#[tokio::test]
async fn expired_approval_is_rejected() {
    let dir = TempDir::new().expect("temp dir");
    let target = dir.path().join("expired_test.txt");

    let grant_store = GrantStore::new();
    let receipt_store = ReceiptStore::new();

    let mut request = ExternalWriteRequest {
        approval_id: Uuid::new_v4(),
        workspace_grant_id: Uuid::new_v4(),
        run_id: Uuid::new_v4(),
        operation: ExternalWriteOperation::CreateFile,
        target_realpath: target.to_string_lossy().to_string(),
        expected_old_sha256: None,
        source_relative_path: None,
        source_sha256: None,
        source_size: None,
        expires_at: "2020-01-01T00:00:00Z".to_owned(),
    };
    configure_request(&mut request, dir.path(), &grant_store, None).await;

    let result = handle_external_write_execute(request, &grant_store, &receipt_store).await;
    assert!(result.is_err(), "expired approval should be rejected");
    let err_msg = result.unwrap_err().to_string();
    assert!(
        err_msg.contains("APPROVAL_EXPIRED"),
        "unexpected error: {err_msg}"
    );
}

#[tokio::test]
async fn sha_mismatch_before_write_is_detected() {
    let dir = TempDir::new().expect("temp dir");
    let target = dir.path().join("mismatch.txt");
    fs::write(&target, b"original content").expect("write original");

    let grant_store = GrantStore::new();
    let receipt_store = ReceiptStore::new();

    let mut request = make_request(
        ExternalWriteOperation::ReplaceFile,
        target.to_string_lossy().to_string(),
        Some("0000000000000000000000000000000000000000000000000000000000000000".to_owned()),
    );
    configure_request(
        &mut request,
        dir.path(),
        &grant_store,
        Some(b"replacement content"),
    )
    .await;

    let result = handle_external_write_execute(request, &grant_store, &receipt_store).await;
    assert!(result.is_err(), "SHA mismatch should be rejected");
    let err_msg = result.unwrap_err().to_string();
    assert!(
        err_msg.contains("APPROVAL_TARGET_CHANGED"),
        "unexpected error: {err_msg}"
    );
}

#[tokio::test]
async fn receipt_idempotency_returns_original_result() {
    let dir = TempDir::new().expect("temp dir");
    let target = dir.path().join("idempotent.txt");

    let grant_store = GrantStore::new();
    let receipt_store = ReceiptStore::new();

    let mut request = make_request(
        ExternalWriteOperation::CreateFile,
        target.to_string_lossy().to_string(),
        None,
    );
    configure_request(
        &mut request,
        dir.path(),
        &grant_store,
        Some(b"created content"),
    )
    .await;

    let first = handle_external_write_execute(request.clone(), &grant_store, &receipt_store)
        .await
        .expect("first execution");

    let second = handle_external_write_execute(request, &grant_store, &receipt_store)
        .await
        .expect("second execution (idempotent)");

    assert_eq!(
        second.result_state_sha256, first.result_state_sha256,
        "idempotent result should have same state hash"
    );
    assert_eq!(
        second.receipt_sha256, first.receipt_sha256,
        "idempotent result should have same receipt hash"
    );
    assert_eq!(
        second.completed_at, first.completed_at,
        "idempotent result should have same timestamp"
    );
}

#[tokio::test]
async fn target_changed_after_receipt_returns_security_risk() {
    let dir = TempDir::new().expect("temp dir");
    let target = dir.path().join("risk.txt");

    let grant_store = GrantStore::new();
    let receipt_store = ReceiptStore::new();

    let mut request = make_request(
        ExternalWriteOperation::CreateFile,
        target.to_string_lossy().to_string(),
        None,
    );
    configure_request(
        &mut request,
        dir.path(),
        &grant_store,
        Some(b"created content"),
    )
    .await;

    let _first = handle_external_write_execute(request.clone(), &grant_store, &receipt_store)
        .await
        .expect("first execution");

    let target_path = PathBuf::from(&request.target_realpath);
    fs::write(&target_path, b"tampered content").expect("tamper with file");

    let result = handle_external_write_execute(request, &grant_store, &receipt_store).await;

    assert!(
        result.is_err(),
        "target changed after receipt should return SECURITY_RISK"
    );
    if let Err(err) = result {
        let msg = err.to_string();
        assert!(msg.contains("SECURITY_RISK"), "unexpected error: {msg}");
    }
}

#[tokio::test]
async fn delete_operation() {
    let dir = TempDir::new().expect("temp dir");
    let target = dir.path().join("delete_me.txt");
    fs::write(&target, b"content to delete").expect("write original");

    let grant_store = GrantStore::new();
    let receipt_store = ReceiptStore::new();
    let old_sha = state_sha_of(&target);

    let mut request = make_request(
        ExternalWriteOperation::DeleteFile,
        target.to_string_lossy().to_string(),
        Some(old_sha),
    );
    configure_request(&mut request, dir.path(), &grant_store, None).await;

    let response = handle_external_write_execute(request, &grant_store, &receipt_store)
        .await
        .expect("delete file");

    assert!(!target.exists(), "file should be deleted");
    assert_eq!(response.operation, ExternalWriteOperation::DeleteFile);
    assert!(!response.receipt_sha256.is_empty());
    assert!(!response.result_state_sha256.is_empty());
}
