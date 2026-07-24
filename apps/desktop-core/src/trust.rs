//! Catalog trust-chain and OfflineSessionTicket verification.

use base64::Engine;
use chrono::{DateTime, Utc};
use ed25519_dalek::{Signature, Verifier, VerifyingKey};
use serde::Deserialize;
use serde_json::{json, Value};
use uuid::Uuid;

use crate::error::AppError;
use crate::rpc::api_client::{AuthKeyset, CatalogKeyset, SigningKey};

const OFFLINE_AUDIENCE: &str = "ibreeze-offline";

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct JwtHeader {
    alg: String,
    typ: String,
    kid: String,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct OfflineClaims {
    iss: String,
    aud: String,
    sub: Uuid,
    device_id: Uuid,
    backend_origin: String,
    iat: i64,
    exp: i64,
    jti: Uuid,
}

pub fn verify_catalog_keyset(
    keyset: &CatalogKeyset,
    development_mode: bool,
    allow_expired: bool,
) -> Result<Vec<SigningKey>, AppError> {
    validate_keyset_window(&keyset.issued_at, &keyset.expires_at, allow_expired)?;
    validate_keys(&keyset.keys)?;
    let payload = canonical_bytes(json!({
        "keys": keyset.keys,
        "issued_at": keyset.issued_at,
        "expires_at": keyset.expires_at,
    }))?;
    let embedded = option_env!("IBREEZE_CATALOG_TRUST_KEY_BASE64");
    if let Some(encoded) = embedded {
        let trusted = decode_verifying_key(encoded)?;
        if keyset.signatures.iter().any(|candidate| {
            candidate.signature_algorithm == "Ed25519"
                && verify_signature(&trusted, &payload, &candidate.signature).is_ok()
        }) {
            return Ok(keyset.keys.clone());
        }
    } else if development_mode {
        for candidate in &keyset.signatures {
            if candidate.signature_algorithm != "Ed25519" {
                continue;
            }
            if let Some(key) = keyset
                .keys
                .iter()
                .find(|key| key.kid == candidate.signing_key_id && key.status == "active")
            {
                let verifying_key = jwk_verifying_key(key)?;
                if verify_signature(&verifying_key, &payload, &candidate.signature).is_ok() {
                    return Ok(keyset.keys.clone());
                }
            }
        }
    } else {
        return Err(AppError::Security(
            "Catalog trust key is not embedded in this build".to_owned(),
        ));
    }
    Err(AppError::Security("CATALOG_SIGNATURE_INVALID".to_owned()))
}

pub fn verify_auth_keyset(
    keyset: &AuthKeyset,
    catalog_keys: &[SigningKey],
    allow_expired: bool,
) -> Result<(), AppError> {
    validate_keyset_window(&keyset.issued_at, &keyset.expires_at, allow_expired)?;
    validate_keys(&keyset.keys)?;
    if keyset.signature_algorithm != "Ed25519" {
        return Err(AppError::Security(
            "Unsupported auth keyset signature".to_owned(),
        ));
    }
    let signing_key = catalog_keys
        .iter()
        .find(|key| key.kid == keyset.signing_key_id)
        .ok_or_else(|| AppError::Security("Auth keyset signer is not trusted".to_owned()))?;
    let payload = canonical_bytes(json!({
        "keys": keyset.keys,
        "issued_at": keyset.issued_at,
        "expires_at": keyset.expires_at,
    }))?;
    verify_signature(
        &jwk_verifying_key(signing_key)?,
        &payload,
        &keyset.signature,
    )
}

pub fn verify_offline_ticket(
    token: &str,
    keyset: &AuthKeyset,
    expected_origin: &str,
    expected_user_id: Uuid,
    expected_device_id: Uuid,
) -> Result<DateTime<Utc>, AppError> {
    let parts: Vec<&str> = token.split('.').collect();
    if parts.len() != 3 {
        return Err(AppError::Security("OFFLINE_TICKET_INVALID".to_owned()));
    }
    let header: JwtHeader = decode_json_segment(parts[0])?;
    if header.alg != "EdDSA" || header.typ != "JWT" {
        return Err(AppError::Security("OFFLINE_TICKET_INVALID".to_owned()));
    }
    let key = keyset
        .keys
        .iter()
        .find(|key| key.kid == header.kid && matches!(key.status.as_str(), "active" | "retiring"))
        .ok_or_else(|| AppError::Security("OFFLINE_TICKET_INVALID".to_owned()))?;
    let signed = format!("{}.{}", parts[0], parts[1]);
    verify_signature(&jwk_verifying_key(key)?, signed.as_bytes(), parts[2])?;
    let claims: OfflineClaims = decode_json_segment(parts[1])?;
    let now = Utc::now().timestamp();
    if claims.iss != expected_origin
        || claims.aud != OFFLINE_AUDIENCE
        || claims.sub != expected_user_id
        || claims.device_id != expected_device_id
        || claims.backend_origin != expected_origin
        || claims.iat > now + 60
        || claims.exp < now - 60
        || claims.exp <= claims.iat
        || claims.jti.is_nil()
    {
        return Err(AppError::Security("OFFLINE_TICKET_INVALID".to_owned()));
    }
    DateTime::from_timestamp(claims.exp, 0)
        .ok_or_else(|| AppError::Security("OFFLINE_TICKET_INVALID".to_owned()))
}

fn validate_keyset_window(
    issued_at: &str,
    expires_at: &str,
    allow_expired: bool,
) -> Result<(), AppError> {
    let issued = DateTime::parse_from_rfc3339(issued_at)
        .map_err(|_| AppError::Security("Invalid keyset timestamp".to_owned()))?
        .with_timezone(&Utc);
    let expires = DateTime::parse_from_rfc3339(expires_at)
        .map_err(|_| AppError::Security("Invalid keyset timestamp".to_owned()))?
        .with_timezone(&Utc);
    let now = Utc::now();
    if issued > now + chrono::Duration::seconds(60)
        || (!allow_expired && expires < now)
        || expires <= issued
    {
        return Err(AppError::Security(
            "Keyset is outside its validity window".to_owned(),
        ));
    }
    Ok(())
}

fn validate_keys(keys: &[SigningKey]) -> Result<(), AppError> {
    if keys.is_empty()
        || keys.iter().any(|key| {
            key.kty != "OKP"
                || key.crv != "Ed25519"
                || key.key_use != "sig"
                || key.alg != "EdDSA"
                || !matches!(key.status.as_str(), "active" | "retiring" | "retired")
        })
    {
        return Err(AppError::Security("Invalid signing keyset".to_owned()));
    }
    Ok(())
}

fn canonical_bytes(value: Value) -> Result<Vec<u8>, AppError> {
    serde_json::to_vec(&value).map_err(|error| AppError::Internal(error.to_string()))
}

fn jwk_verifying_key(key: &SigningKey) -> Result<VerifyingKey, AppError> {
    decode_verifying_key(&key.x)
}

fn decode_verifying_key(encoded: &str) -> Result<VerifyingKey, AppError> {
    let raw = base64::engine::general_purpose::URL_SAFE_NO_PAD
        .decode(encoded)
        .map_err(|_| AppError::Security("Invalid Ed25519 public key".to_owned()))?;
    let bytes: [u8; 32] = raw
        .try_into()
        .map_err(|_| AppError::Security("Invalid Ed25519 public key".to_owned()))?;
    VerifyingKey::from_bytes(&bytes)
        .map_err(|_| AppError::Security("Invalid Ed25519 public key".to_owned()))
}

fn verify_signature(
    key: &VerifyingKey,
    payload: &[u8],
    encoded_signature: &str,
) -> Result<(), AppError> {
    let raw = base64::engine::general_purpose::URL_SAFE_NO_PAD
        .decode(encoded_signature)
        .map_err(|_| AppError::Security("Invalid Ed25519 signature".to_owned()))?;
    let signature = Signature::from_slice(&raw)
        .map_err(|_| AppError::Security("Invalid Ed25519 signature".to_owned()))?;
    key.verify(payload, &signature)
        .map_err(|_| AppError::Security("CATALOG_SIGNATURE_INVALID".to_owned()))
}

fn decode_json_segment<T: for<'de> Deserialize<'de>>(segment: &str) -> Result<T, AppError> {
    let bytes = base64::engine::general_purpose::URL_SAFE_NO_PAD
        .decode(segment)
        .map_err(|_| AppError::Security("OFFLINE_TICKET_INVALID".to_owned()))?;
    serde_json::from_slice(&bytes)
        .map_err(|_| AppError::Security("OFFLINE_TICKET_INVALID".to_owned()))
}

#[cfg(test)]
mod tests {
    use super::*;
    use ed25519_dalek::{Signer, SigningKey};

    fn encoded(value: &[u8]) -> String {
        base64::engine::general_purpose::URL_SAFE_NO_PAD.encode(value)
    }

    fn signing_key(seed: u8) -> SigningKey {
        SigningKey::from_bytes(&[seed; 32])
    }

    fn public_key_info(key: &SigningKey, kid: &str) -> crate::rpc::api_client::SigningKey {
        crate::rpc::api_client::SigningKey {
            kty: "OKP".to_owned(),
            crv: "Ed25519".to_owned(),
            kid: kid.to_owned(),
            key_use: "sig".to_owned(),
            alg: "EdDSA".to_owned(),
            x: encoded(key.verifying_key().as_bytes()),
            status: "active".to_owned(),
        }
    }

    #[test]
    fn development_chain_and_offline_ticket_are_verified() {
        let catalog_signer = signing_key(7);
        let auth_signer = signing_key(9);
        let now = Utc::now();
        let issued_at = now.to_rfc3339();
        let expires_at = (now + chrono::Duration::hours(1)).to_rfc3339();
        let catalog_key = public_key_info(&catalog_signer, "catalog-1");
        let catalog_payload = canonical_bytes(json!({
            "keys": [catalog_key.clone()],
            "issued_at": issued_at,
            "expires_at": expires_at,
        }))
        .expect("catalog payload");
        let catalog_keyset = CatalogKeyset {
            keys: vec![catalog_key],
            issued_at: issued_at.clone(),
            expires_at: expires_at.clone(),
            signatures: vec![crate::rpc::api_client::KeysetSignature {
                signing_key_id: "catalog-1".to_owned(),
                signature_algorithm: "Ed25519".to_owned(),
                signature: encoded(&catalog_signer.sign(&catalog_payload).to_bytes()),
            }],
        };
        let trusted = verify_catalog_keyset(&catalog_keyset, true, false).expect("catalog keyset");

        let auth_key = public_key_info(&auth_signer, "auth-1");
        let auth_payload = canonical_bytes(json!({
            "keys": [auth_key.clone()],
            "issued_at": issued_at,
            "expires_at": expires_at,
        }))
        .expect("auth payload");
        let auth_keyset = AuthKeyset {
            keys: vec![auth_key],
            issued_at,
            expires_at,
            signing_key_id: "catalog-1".to_owned(),
            signature_algorithm: "Ed25519".to_owned(),
            signature: encoded(&catalog_signer.sign(&auth_payload).to_bytes()),
        };
        verify_auth_keyset(&auth_keyset, &trusted, false).expect("auth keyset");

        let user_id = Uuid::new_v4();
        let device_id = Uuid::new_v4();
        let origin = "https://example.com:443";
        let header = encoded(
            serde_json::to_string(&json!({"alg":"EdDSA","kid":"auth-1","typ":"JWT"}))
                .expect("header")
                .as_bytes(),
        );
        let claims = encoded(
            serde_json::to_string(&json!({
                "aud": OFFLINE_AUDIENCE,
                "backend_origin": origin,
                "device_id": device_id,
                "exp": now.timestamp() + 3600,
                "iat": now.timestamp(),
                "iss": origin,
                "jti": Uuid::new_v4(),
                "sub": user_id,
            }))
            .expect("claims")
            .as_bytes(),
        );
        let signed = format!("{header}.{claims}");
        let token = format!(
            "{signed}.{}",
            encoded(&auth_signer.sign(signed.as_bytes()).to_bytes())
        );
        assert!(verify_offline_ticket(&token, &auth_keyset, origin, user_id, device_id).is_ok());
        assert!(
            verify_offline_ticket(&token, &auth_keyset, origin, user_id, Uuid::new_v4()).is_err()
        );
    }
}
