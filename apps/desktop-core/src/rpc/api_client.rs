//! Hardened Backend REST client. Authentication secrets never enter WebView state.

use std::time::Duration;

use reqwest::{redirect, Method, Response};
use serde::{de::DeserializeOwned, Deserialize, Serialize};
use url::Url;
use uuid::Uuid;

use crate::error::AppError;

const MAX_RESPONSE_BYTES: usize = 16 * 1024 * 1024;

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Envelope<T> {
    pub data: Option<T>,
    pub meta: Option<ResponseMeta>,
    pub error: Option<ErrorBody>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ResponseMeta {
    pub request_id: String,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ErrorBody {
    #[serde(rename = "type")]
    pub error_type: String,
    pub title: String,
    pub status: u16,
    pub code: String,
    pub detail: String,
    pub request_id: Option<String>,
    pub field_errors: Option<serde_json::Value>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct UserInfo {
    pub id: Uuid,
    pub user_type: String,
    pub username: Option<String>,
    pub email: Option<String>,
    pub display_name: String,
    pub masked_identifier: String,
    pub status: String,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RegisterData {
    pub user: UserInfo,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SessionData {
    pub user: UserInfo,
    pub access_token: String,
    pub access_token_expires_in: u64,
    pub family_id: Uuid,
    pub pwd_change_required: bool,
    pub refresh_token: Option<String>,
    pub refresh_token_expires_in: Option<u64>,
    pub offline_session_ticket: Option<String>,
    pub offline_session_ticket_expires_in: Option<u64>,
}

#[derive(Debug, Serialize)]
#[serde(deny_unknown_fields)]
struct RegisterRequest<'a> {
    email: &'a str,
    password: &'a str,
}

#[derive(Debug, Serialize)]
#[serde(deny_unknown_fields)]
struct LoginRequest<'a> {
    identifier: &'a str,
    password: &'a str,
    device_id: Uuid,
}

#[derive(Debug, Serialize)]
#[serde(deny_unknown_fields)]
struct RefreshRequest<'a> {
    refresh_token: &'a str,
}

#[derive(Debug, Serialize)]
#[serde(deny_unknown_fields)]
struct ChangePasswordRequest<'a> {
    current_password: &'a str,
    new_password: &'a str,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ReadyResponse {
    pub status: String,
    pub database: String,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CatalogManifest {
    pub release_sequence: u64,
    pub resources: Vec<serde_json::Value>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SigningKey {
    pub kty: String,
    pub crv: String,
    pub kid: String,
    #[serde(rename = "use")]
    pub key_use: String,
    pub alg: String,
    pub x: String,
    pub status: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct KeysetSignature {
    pub signing_key_id: String,
    pub signature_algorithm: String,
    pub signature: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CatalogKeyset {
    pub keys: Vec<SigningKey>,
    pub issued_at: String,
    pub expires_at: String,
    pub signatures: Vec<KeysetSignature>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AuthKeyset {
    pub keys: Vec<SigningKey>,
    pub issued_at: String,
    pub expires_at: String,
    pub signing_key_id: String,
    pub signature_algorithm: String,
    pub signature: String,
}

pub struct ApiClient {
    origin: Url,
    client: reqwest::Client,
}

impl ApiClient {
    pub fn new(origin: &str, development_mode: bool) -> Result<Self, AppError> {
        let canonical = canonicalize_origin(origin, development_mode)?;
        let parsed =
            Url::parse(&canonical).map_err(|error| AppError::Validation(error.to_string()))?;
        let redirect_origin = canonical.clone();
        let client = reqwest::Client::builder()
            .connect_timeout(Duration::from_secs(5))
            .timeout(Duration::from_secs(30))
            .redirect(redirect::Policy::custom(move |attempt| {
                if attempt.previous().len() >= 3 {
                    return attempt.stop();
                }
                let url = attempt.url();
                let candidate = format!(
                    "{}://{}:{}",
                    url.scheme(),
                    url.host_str().unwrap_or_default(),
                    url.port_or_known_default().unwrap_or_default(),
                );
                if url.scheme() == "https" && candidate == redirect_origin {
                    attempt.follow()
                } else {
                    attempt.stop()
                }
            }))
            .build()
            .map_err(|error| AppError::Network(error.to_string()))?;
        Ok(Self {
            origin: parsed,
            client,
        })
    }

    pub fn canonical_origin(&self) -> String {
        self.origin.as_str().trim_end_matches('/').to_owned()
    }

    pub async fn ready(&self) -> Result<ReadyResponse, AppError> {
        let response = self
            .client
            .get(self.url("/health/ready")?)
            .send()
            .await
            .map_err(|error| AppError::Network(error.to_string()))?;
        let ready: ReadyResponse = decode_response(response).await?;
        if ready.status != "ready" || ready.database != "connected" {
            return Err(AppError::Network(
                "Backend readiness check failed".to_owned(),
            ));
        }
        Ok(ready)
    }

    pub async fn register(&self, email: &str, password: &str) -> Result<RegisterData, AppError> {
        self.envelope(
            Method::POST,
            "/api/v1/auth/register",
            Some(&RegisterRequest { email, password }),
            None,
        )
        .await
    }

    pub async fn login(
        &self,
        email: &str,
        password: &str,
        device_id: Uuid,
    ) -> Result<SessionData, AppError> {
        self.envelope(
            Method::POST,
            "/api/v1/auth/login",
            Some(&LoginRequest {
                identifier: email,
                password,
                device_id,
            }),
            None,
        )
        .await
    }

    pub async fn refresh(&self, refresh_token: &str) -> Result<SessionData, AppError> {
        self.envelope(
            Method::POST,
            "/api/v1/auth/refresh",
            Some(&RefreshRequest { refresh_token }),
            None,
        )
        .await
    }

    pub async fn change_password(
        &self,
        access_token: &str,
        current_password: &str,
        new_password: &str,
    ) -> Result<SessionData, AppError> {
        self.envelope(
            Method::POST,
            "/api/v1/auth/change-password",
            Some(&ChangePasswordRequest {
                current_password,
                new_password,
            }),
            Some(access_token),
        )
        .await
    }

    pub async fn logout(&self, access_token: &str) -> Result<(), AppError> {
        let response = self
            .client
            .post(self.url("/api/v1/auth/logout")?)
            .bearer_auth(access_token)
            .send()
            .await
            .map_err(|error| AppError::Network(error.to_string()))?;
        if response.status() == reqwest::StatusCode::NO_CONTENT {
            return Ok(());
        }
        Err(http_error(response).await)
    }

    pub async fn latest_catalog_manifest(&self) -> Result<CatalogManifest, AppError> {
        let response = self
            .client
            .get(self.url("/api/v1/catalog/manifest")?)
            .send()
            .await
            .map_err(|error| AppError::Network(error.to_string()))?;
        decode_response(response).await
    }

    pub async fn catalog_keys(&self) -> Result<CatalogKeyset, AppError> {
        let response = self
            .client
            .get(self.url("/api/v1/catalog/keys")?)
            .send()
            .await
            .map_err(|error| AppError::Network(error.to_string()))?;
        decode_response(response).await
    }

    pub async fn auth_keys(&self) -> Result<AuthKeyset, AppError> {
        self.envelope::<AuthKeyset, serde_json::Value>(Method::GET, "/api/v1/auth/keys", None, None)
            .await
    }

    async fn envelope<T, B>(
        &self,
        method: Method,
        path: &str,
        body: Option<&B>,
        access_token: Option<&str>,
    ) -> Result<T, AppError>
    where
        T: DeserializeOwned,
        B: Serialize + ?Sized,
    {
        let mut request = self.client.request(method, self.url(path)?);
        if let Some(body) = body {
            request = request.json(body);
        }
        if let Some(token) = access_token {
            request = request.bearer_auth(token);
        }
        let response = request
            .send()
            .await
            .map_err(|error| AppError::Network(error.to_string()))?;
        let envelope: Envelope<T> = decode_response(response).await?;
        if let Some(error) = envelope.error {
            return Err(AppError::Auth(format!("{}: {}", error.code, error.detail)));
        }
        envelope
            .data
            .ok_or_else(|| AppError::Network("Backend response data is missing".to_owned()))
    }

    fn url(&self, path: &str) -> Result<Url, AppError> {
        self.origin
            .join(path)
            .map_err(|error| AppError::Validation(error.to_string()))
    }
}

pub fn canonicalize_origin(origin: &str, development_mode: bool) -> Result<String, AppError> {
    let parsed = Url::parse(origin.trim())
        .map_err(|_| AppError::Validation("Backend Origin is invalid".to_owned()))?;
    if !parsed.username().is_empty()
        || parsed.password().is_some()
        || parsed.query().is_some()
        || parsed.fragment().is_some()
        || parsed.path() != "/"
    {
        return Err(AppError::Validation(
            "Backend Origin must not contain credentials, path, query or fragment".to_owned(),
        ));
    }
    let host = parsed
        .host_str()
        .ok_or_else(|| AppError::Validation("Backend Origin host is missing".to_owned()))?
        .to_ascii_lowercase();
    let is_dev_loopback = development_mode && parsed.scheme() == "http" && host == "127.0.0.1";
    if parsed.scheme() != "https" && !is_dev_loopback {
        return Err(AppError::Validation(
            "Backend Origin must use HTTPS".to_owned(),
        ));
    }
    let port = parsed
        .port_or_known_default()
        .ok_or_else(|| AppError::Validation("Backend Origin port is invalid".to_owned()))?;
    Ok(format!("{}://{}:{}", parsed.scheme(), host, port))
}

async fn decode_response<T: DeserializeOwned>(response: Response) -> Result<T, AppError> {
    if !response.status().is_success() {
        return Err(http_error(response).await);
    }
    let body = read_body(response).await?;
    serde_json::from_slice(&body)
        .map_err(|error| AppError::Network(format!("invalid Backend response: {error}")))
}

async fn read_body(mut response: Response) -> Result<Vec<u8>, AppError> {
    let mut body = Vec::new();
    while let Some(chunk) = response
        .chunk()
        .await
        .map_err(|error| AppError::Network(error.to_string()))?
    {
        if body.len() + chunk.len() > MAX_RESPONSE_BYTES {
            return Err(AppError::Network(
                "Backend response exceeds 16 MiB".to_owned(),
            ));
        }
        body.extend_from_slice(&chunk);
    }
    Ok(body)
}

async fn http_error(response: Response) -> AppError {
    let status = response.status();
    let envelope = match read_body(response).await {
        Ok(body) => serde_json::from_slice::<Envelope<serde_json::Value>>(&body).ok(),
        Err(_) => None,
    };
    match envelope {
        Some(envelope) => match envelope.error {
            Some(error) => AppError::Auth(format!("{}: {}", error.code, error.detail)),
            None => AppError::Network(format!("Backend returned HTTP {status}")),
        },
        None => AppError::Network(format!("Backend returned HTTP {status}")),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn origin_is_canonical_and_explicitly_ported() {
        assert_eq!(
            canonicalize_origin("https://EXAMPLE.com", false).expect("valid origin"),
            "https://example.com:443"
        );
        assert_eq!(
            canonicalize_origin("http://127.0.0.1", true).expect("valid dev origin"),
            "http://127.0.0.1:80"
        );
    }

    #[test]
    fn origin_rejects_path_credentials_and_insecure_remote() {
        for origin in [
            "https://example.com/path",
            "https://user@example.com",
            "http://example.com",
        ] {
            assert!(canonicalize_origin(origin, false).is_err(), "{origin}");
        }
    }
}
