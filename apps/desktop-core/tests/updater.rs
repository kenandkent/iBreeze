use base64::Engine;
use chrono::{DateTime, Utc};
use ed25519_dalek::Signer;
use ibreeze_desktop_core::rpc::api_client::SigningKey;
use ibreeze_desktop_core::update::manifest::{
    is_newer_version, verify_manifest_signature, verify_package_sha256, verify_package_url,
    verify_version_constraints, UpdateManifest,
};
use ibreeze_desktop_core::update::rollback::UpdateStore;
use sha2::Digest;

fn encoded_standard(value: &[u8]) -> String {
    base64::engine::general_purpose::STANDARD.encode(value)
}

fn encoded_url(value: &[u8]) -> String {
    base64::engine::general_purpose::URL_SAFE_NO_PAD.encode(value)
}

fn make_signing_key(seed: u8) -> ed25519_dalek::SigningKey {
    ed25519_dalek::SigningKey::from_bytes(&[seed; 32])
}

fn make_manifest(signer: Option<&ed25519_dalek::SigningKey>) -> UpdateManifest {
    let published = DateTime::parse_from_rfc3339("2024-06-15T10:00:00Z")
        .unwrap()
        .with_timezone(&Utc);
    let mut manifest = UpdateManifest {
        version: "0.2.0".to_owned(),
        minimum_current_version: "0.1.0".to_owned(),
        package_url: "https://releases.ibreeze.ai/download/ibreeze-0.2.0.tar.gz".to_owned(),
        package_sha256: "d2hvbGVzYWx0".to_owned(),
        signature: String::new(),
        published_at: published,
    };
    if let Some(key) = signer {
        let payload = serde_json::json!({
            "version": manifest.version,
            "minimum_current_version": manifest.minimum_current_version,
            "package_url": manifest.package_url,
            "package_sha256": manifest.package_sha256,
            "published_at": manifest.published_at.to_rfc3339(),
        });
        let canonical = serde_json::to_vec(&payload).unwrap();
        let sig = key.sign(&canonical);
        manifest.signature = encoded_standard(&sig.to_bytes());
    }
    manifest
}

fn active_signing_key(key: &ed25519_dalek::SigningKey, kid: &str) -> SigningKey {
    SigningKey {
        kty: "OKP".to_owned(),
        crv: "Ed25519".to_owned(),
        kid: kid.to_owned(),
        key_use: "sig".to_owned(),
        alg: "EdDSA".to_owned(),
        x: encoded_url(key.verifying_key().as_bytes()),
        status: "active".to_owned(),
    }
}

#[test]
fn valid_signature_is_accepted() {
    let signer = make_signing_key(1);
    let manifest = make_manifest(Some(&signer));
    let trusted = vec![active_signing_key(&signer, "key-1")];
    assert!(verify_manifest_signature(&manifest, &trusted).is_ok());
}

#[test]
fn tampered_signature_is_rejected() {
    let signer = make_signing_key(1);
    let mut manifest = make_manifest(Some(&signer));
    manifest.signature = encoded_standard(&[0u8; 64]);
    let trusted = vec![active_signing_key(&signer, "key-1")];
    assert!(verify_manifest_signature(&manifest, &trusted).is_err());
}

#[test]
fn missing_signature_is_rejected() {
    let signer = make_signing_key(1);
    let manifest = make_manifest(Some(&signer));
    let trusted: Vec<SigningKey> = vec![];
    assert!(verify_manifest_signature(&manifest, &trusted).is_err());
}

#[test]
fn wrong_signer_is_rejected() {
    let signer_a = make_signing_key(1);
    let signer_b = make_signing_key(2);
    let manifest = make_manifest(Some(&signer_a));
    let trusted = vec![active_signing_key(&signer_b, "key-b")];
    assert!(verify_manifest_signature(&manifest, &trusted).is_err());
}

#[test]
fn retired_key_does_not_validate() {
    let signer = make_signing_key(1);
    let manifest = make_manifest(Some(&signer));
    let trusted = vec![SigningKey {
        kty: "OKP".to_owned(),
        crv: "Ed25519".to_owned(),
        kid: "key-retired".to_owned(),
        key_use: "sig".to_owned(),
        alg: "EdDSA".to_owned(),
        x: encoded_url(signer.verifying_key().as_bytes()),
        status: "retired".to_owned(),
    }];
    assert!(verify_manifest_signature(&manifest, &trusted).is_err());
}

#[test]
fn package_sha_verification_accepts_valid() {
    let data = b"hello world";
    let mut hasher = sha2::Sha256::new();
    hasher.update(data);
    let hash = base64::engine::general_purpose::STANDARD.encode(hasher.finalize());
    assert!(verify_package_sha256(data, &hash).is_ok());
}

#[test]
fn package_sha_verification_rejects_tampered() {
    let data = b"hello world";
    let bad_hash = base64::engine::general_purpose::STANDARD.encode([0u8; 32]);
    assert!(verify_package_sha256(data, &bad_hash).is_err());
}

#[test]
fn version_constraints_accept_upgrade() {
    let manifest = make_manifest(None);
    assert!(verify_version_constraints(&manifest, "0.1.0").is_ok());
}

#[test]
fn version_constraints_reject_downgrade() {
    let manifest = make_manifest(None);
    let upd: UpdateManifest = UpdateManifest {
        version: "0.0.9".to_owned(),
        ..manifest
    };
    assert!(verify_version_constraints(&upd, "0.1.0").is_err());
}

#[test]
fn version_constraints_reject_minimum_not_met() {
    let manifest = make_manifest(None);
    let upd: UpdateManifest = UpdateManifest {
        minimum_current_version: "0.3.0".to_owned(),
        ..manifest
    };
    assert!(verify_version_constraints(&upd, "0.1.0").is_err());
}

#[test]
fn version_constraints_reject_equal_versions() {
    let manifest = make_manifest(None);
    let upd: UpdateManifest = UpdateManifest {
        version: "0.1.0".to_owned(),
        ..manifest
    };
    assert!(verify_version_constraints(&upd, "0.1.0").is_err());
}

#[test]
fn valid_https_url_is_accepted() {
    let manifest = make_manifest(None);
    assert!(verify_package_url(&manifest).is_ok());
}

#[test]
fn http_url_is_rejected() {
    let manifest = make_manifest(None);
    let upd: UpdateManifest = UpdateManifest {
        package_url: "http://releases.ibreeze.ai/download/pkg.tar.gz".to_owned(),
        ..manifest
    };
    assert!(verify_package_url(&upd).is_err());
}

#[test]
fn localhost_url_is_rejected() {
    let manifest = make_manifest(None);
    let upd: UpdateManifest = UpdateManifest {
        package_url: "https://localhost/pkg.tar.gz".to_owned(),
        ..manifest
    };
    assert!(verify_package_url(&upd).is_err());
}

#[test]
fn invalid_extension_is_rejected() {
    let manifest = make_manifest(None);
    let upd: UpdateManifest = UpdateManifest {
        package_url: "https://releases.ibreeze.ai/download/package.exe".to_owned(),
        ..manifest
    };
    assert!(verify_package_url(&upd).is_err());
}

#[test]
fn is_newer_version_returns_true_for_minor_upgrade() {
    assert!(is_newer_version("0.2.0", "0.1.0"));
}

#[test]
fn is_newer_version_returns_false_for_equal() {
    assert!(!is_newer_version("0.1.0", "0.1.0"));
}

#[test]
fn is_newer_version_returns_false_for_older() {
    assert!(!is_newer_version("0.0.9", "0.1.0"));
}

#[tokio::test]
async fn verify_pending_update_returns_true_when_no_marker() {
    let temp = tempfile::tempdir().unwrap();
    let store = UpdateStore::new(temp.path().to_path_buf());
    let sidecar = temp.path().join("sidecar");
    let socket = temp.path().join("sidecar.sock");

    let result = store
        .verify_pending_update(&sidecar, "0.2.0", &socket)
        .await
        .unwrap();
    assert!(result);
}

#[tokio::test]
async fn verify_pending_update_returns_false_when_sidecar_missing() {
    let temp = tempfile::tempdir().unwrap();
    let store = UpdateStore::new(temp.path().to_path_buf());
    let sidecar = temp.path().join("nonexistent_sidecar");
    let socket = temp.path().join("sidecar.sock");

    store
        .create_pending_marker("0.1.0", "0.2.0", "backup-1", "sha256hash")
        .unwrap();

    let result = store
        .verify_pending_update(&sidecar, "0.2.0", &socket)
        .await
        .unwrap();
    assert!(!result);
}

#[tokio::test]
async fn verify_pending_update_returns_false_when_version_mismatch() {
    let temp = tempfile::tempdir().unwrap();
    let store = UpdateStore::new(temp.path().to_path_buf());
    let sidecar = temp.path().join("sidecar");
    let socket = temp.path().join("sidecar.sock");

    std::fs::write(&sidecar, b"fake sidecar").unwrap();
    store
        .create_pending_marker("0.1.0", "0.2.0", "backup-1", "sha256hash")
        .unwrap();

    let result = store
        .verify_pending_update(&sidecar, "0.3.0", &socket)
        .await
        .unwrap();
    assert!(!result);
}

#[tokio::test]
async fn verify_pending_update_triggers_rollback_when_health_check_fails() {
    let temp = tempfile::tempdir().unwrap();
    let store = UpdateStore::new(temp.path().to_path_buf());
    let sidecar = temp.path().join("sidecar");
    let socket = temp.path().join("nonexistent.sock");

    std::fs::write(&sidecar, b"fake sidecar").unwrap();
    store
        .create_pending_marker("0.1.0", "0.2.0", "backup-1", "sha256hash")
        .unwrap();

    let obs_path = store.health_observation_path();
    let obs = serde_json::json!({
        "started_at": (chrono::Utc::now() - chrono::Duration::seconds(31)).to_rfc3339()
    });
    std::fs::write(&obs_path, serde_json::to_vec(&obs).unwrap()).unwrap();

    let result = store
        .verify_pending_update(&sidecar, "0.2.0", &socket)
        .await
        .unwrap();

    assert!(!result);
    assert!(store.load_pending_marker().unwrap().is_none());
    assert!(store.load_stable_version().unwrap().is_none());
}

#[tokio::test]
async fn verify_pending_update_in_progress_returns_true() {
    let temp = tempfile::tempdir().unwrap();
    let store = UpdateStore::new(temp.path().to_path_buf());
    let sidecar = temp.path().join("sidecar");
    let socket = temp.path().join("sidecar.sock");

    std::fs::write(&sidecar, b"fake sidecar").unwrap();
    store
        .create_pending_marker("0.1.0", "0.2.0", "backup-1", "sha256hash")
        .unwrap();

    let obs_path = store.health_observation_path();
    let obs = serde_json::json!({
        "started_at": (chrono::Utc::now() - chrono::Duration::seconds(10)).to_rfc3339()
    });
    std::fs::write(&obs_path, serde_json::to_vec(&obs).unwrap()).unwrap();

    let result = store
        .verify_pending_update(&sidecar, "0.2.0", &socket)
        .await
        .unwrap();

    assert!(result);
    assert!(store.load_pending_marker().unwrap().is_some());
    assert!(store.load_stable_version().unwrap().is_none());
}

#[test]
fn create_and_load_pending_marker() {
    let temp = tempfile::tempdir().unwrap();
    let store = UpdateStore::new(temp.path().to_path_buf());

    store
        .create_pending_marker("0.1.0", "0.2.0", "backup-1", "sha256hash")
        .unwrap();

    let marker = store.load_pending_marker().unwrap().unwrap();
    assert_eq!(marker.old_version, "0.1.0");
    assert_eq!(marker.new_version, "0.2.0");
    assert_eq!(marker.backup_id, "backup-1");
    assert_eq!(marker.stable_package_sha, "sha256hash");
}

#[test]
fn delete_pending_marker_removes_file() {
    let temp = tempfile::tempdir().unwrap();
    let store = UpdateStore::new(temp.path().to_path_buf());

    store
        .create_pending_marker("0.1.0", "0.2.0", "backup-1", "sha256hash")
        .unwrap();
    assert!(store.load_pending_marker().unwrap().is_some());

    store.delete_pending_marker().unwrap();
    assert!(store.load_pending_marker().unwrap().is_none());
}

#[test]
fn mark_stable_records_version() {
    let temp = tempfile::tempdir().unwrap();
    let store = UpdateStore::new(temp.path().to_path_buf());

    store.mark_stable("0.2.0").unwrap();
    assert_eq!(
        store.load_stable_version().unwrap(),
        Some("0.2.0".to_owned())
    );
}

#[test]
fn restore_backup_uses_safe_extract() {
    let temp = tempfile::tempdir().unwrap();
    let store = UpdateStore::new(temp.path().to_path_buf());

    let backup_dir = store.backups_path().join("backup-1");
    std::fs::create_dir_all(&backup_dir).unwrap();

    let archive = backup_dir.join("bundle.tar.gz");
    std::process::Command::new("tar")
        .arg("-czf")
        .arg(&archive)
        .arg("-C")
        .arg(temp.path())
        .arg(".")
        .status()
        .unwrap();

    let install_dir = temp.path().join("install");
    std::fs::create_dir_all(&install_dir).unwrap();

    store.restore_backup(&install_dir, "backup-1").unwrap();
    assert!(install_dir.join("update").exists());
}
