use base64::Engine;
use chrono::{DateTime, Utc};
use ed25519_dalek::{Signature, Verifier, VerifyingKey};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use tracing::{error, info, warn};
use url::Url;

use crate::error::AppError;
use crate::rpc::api_client::SigningKey;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UpdateManifest {
    pub version: String,
    pub minimum_current_version: String,
    pub package_url: String,
    pub package_sha256: String,
    pub signature: String,
    pub published_at: DateTime<Utc>,
}

pub fn verify_manifest_signature(
    manifest: &UpdateManifest,
    trusted_keys: &[SigningKey],
) -> Result<(), AppError> {
    if trusted_keys.is_empty() {
        return Err(AppError::Security(
            "UPDATE_NO_TRUSTED_KEYS: no trusted signing keys configured".to_owned(),
        ));
    }
    let payload = manifest_payload(manifest);
    let raw_signature = base64::engine::general_purpose::STANDARD
        .decode(&manifest.signature)
        .map_err(|_| AppError::Security("UPDATE_SIGNATURE_DECODE_FAILED".to_owned()))?;
    let signature = Signature::from_slice(&raw_signature)
        .map_err(|_| AppError::Security("UPDATE_SIGNATURE_INVALID".to_owned()))?;

    for key in trusted_keys {
        if key.status != "active" {
            continue;
        }
        let raw_key = match base64::engine::general_purpose::URL_SAFE_NO_PAD.decode(&key.x) {
            Ok(v) => v,
            Err(_) => continue,
        };
        if raw_key.len() != 32 {
            continue;
        }
        let mut bytes = [0u8; 32];
        bytes.copy_from_slice(&raw_key);
        if let Ok(verifying_key) = VerifyingKey::from_bytes(&bytes) {
            if verifying_key.verify(&payload, &signature).is_ok() {
                return Ok(());
            }
        }
    }
    error!("UPDATE_SIGNATURE_NO_MATCHING_KEY");
    Err(AppError::Security("UPDATE_SIGNATURE_INVALID".to_owned()))
}

pub fn verify_version_constraints(
    manifest: &UpdateManifest,
    current_version: &str,
) -> Result<(), AppError> {
    if !is_newer_version(&manifest.version, current_version) {
        warn!(current = %current_version, target = %manifest.version, "UPDATE_VERSION_DOWNGRADE_REJECTED");
        return Err(AppError::Validation(
            "UPDATE_VERSION_DOWNGRADE_REJECTED".to_owned(),
        ));
    }
    if is_newer_version(&manifest.minimum_current_version, current_version) {
        warn!(current = %current_version, min = %manifest.minimum_current_version, "UPDATE_VERSION_MINIMUM_NOT_MET");
        return Err(AppError::Validation(
            "UPDATE_VERSION_MINIMUM_NOT_MET".to_owned(),
        ));
    }
    info!(version = %manifest.version, "UPDATE_VERSION_CONSTRAINTS_OK");
    Ok(())
}

pub fn verify_package_url(manifest: &UpdateManifest) -> Result<(), AppError> {
    let parsed = Url::parse(&manifest.package_url)
        .map_err(|_| AppError::Validation("UPDATE_INVALID_PACKAGE_URL".to_owned()))?;
    let scheme = parsed.scheme();
    if scheme != "https" {
        warn!(scheme = %scheme, "UPDATE_URL_SCHEME_REJECTED");
        return Err(AppError::Validation(
            "UPDATE_URL_SCHEME_REJECTED".to_owned(),
        ));
    }
    let host = parsed.host_str().unwrap_or("");
    if host.is_empty() || host == "localhost" || host == "127.0.0.1" {
        warn!(host = %host, "UPDATE_URL_HOST_REJECTED");
        return Err(AppError::Validation("UPDATE_URL_HOST_REJECTED".to_owned()));
    }
    let ext = parsed
        .path_segments()
        .and_then(|mut s| s.next_back())
        .and_then(|name| name.rsplit('.').next())
        .unwrap_or("");
    if ext != "tar" && ext != "gz" && ext != "bz2" && ext != "zip" && ext != "dmg" {
        warn!(extension = %ext, "UPDATE_URL_EXTENSION_REJECTED");
        return Err(AppError::Validation(
            "UPDATE_URL_EXTENSION_REJECTED".to_owned(),
        ));
    }
    Ok(())
}

pub fn verify_package_sha256(package_bytes: &[u8], expected_sha256: &str) -> Result<(), AppError> {
    let mut hasher = Sha256::new();
    hasher.update(package_bytes);
    let actual = base64::engine::general_purpose::STANDARD.encode(hasher.finalize());
    if actual != expected_sha256 {
        warn!("UPDATE_SHA256_MISMATCH");
        return Err(AppError::Security("UPDATE_SHA256_MISMATCH".to_owned()));
    }
    info!("UPDATE_SHA256_OK");
    Ok(())
}

pub fn validate_manifest(
    manifest: &UpdateManifest,
    current_version: &str,
    trusted_keys: &[SigningKey],
    package_bytes: &[u8],
) -> Result<(), AppError> {
    verify_version_constraints(manifest, current_version)?;
    verify_package_url(manifest)?;
    verify_package_sha256(package_bytes, &manifest.package_sha256)?;
    verify_manifest_signature(manifest, trusted_keys)?;
    info!("UPDATE_MANIFEST_FULLY_VALIDATED");
    Ok(())
}

fn manifest_payload(manifest: &UpdateManifest) -> Vec<u8> {
    let canonical = serde_json::json!({
        "version": manifest.version,
        "minimum_current_version": manifest.minimum_current_version,
        "package_url": manifest.package_url,
        "package_sha256": manifest.package_sha256,
        "published_at": manifest.published_at.to_rfc3339(),
    });
    serde_json::to_vec(&canonical).unwrap_or_default()
}

pub fn is_newer_version(target: &str, current: &str) -> bool {
    let target_parts: Vec<u32> = target
        .split('.')
        .filter_map(|p| p.parse::<u32>().ok())
        .collect();
    let current_parts: Vec<u32> = current
        .split('.')
        .filter_map(|p| p.parse::<u32>().ok())
        .collect();
    for (t, c) in target_parts.iter().zip(current_parts.iter()) {
        if t != c {
            return t > c;
        }
    }
    target_parts.len() > current_parts.len()
}
