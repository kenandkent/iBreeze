//! WebView-visible Rust Core response contracts. No secret fields are exposed.

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct BackendValidation {
    pub canonical_origin: String,
    pub ready: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct RegisterResult {
    pub app_user_id: String,
    pub email: String,
    pub masked_identifier: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct LoginResult {
    pub status: String,
    pub profile_directory_id: Option<String>,
    pub masked_identifier: String,
    pub catalog_release_sequence: Option<u64>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct CloseProfileResult {
    pub closed_profile: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct LogoutResult {
    pub closed_profile: bool,
    pub revoked_family: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct OfflineProfile {
    pub profile_directory_id: String,
    pub backend_origin: String,
    pub masked_identifier: String,
    pub expires_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct OfflineProfilesResult {
    pub profiles: Vec<OfflineProfile>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct OpenProfileResult {
    pub profile_directory_id: String,
    pub mode: String,
    pub catalog_release_sequence: u64,
}
