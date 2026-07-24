//! Tauri command boundary. Rust-owned methods never enter the Sidecar.

use std::path::PathBuf;
use std::sync::Arc;

use chrono::{SecondsFormat, Utc};
use serde_json::Value;
use tauri::State;
use tokio::sync::RwLock;
use uuid::Uuid;
use zeroize::Zeroizing;

use crate::error::AppError;
use crate::keyring::{SecureKeyring, SessionBundle};
use crate::rpc::api_client::ApiClient;
use crate::sidecar::{SidecarProfile, SidecarSupervisor};
use crate::store::{profile_directory_id, LocalStore, ProfileMeta};
use crate::trust::{verify_auth_keyset, verify_catalog_keyset, verify_offline_ticket};
use crate::types::{
    BackendValidation, CloseProfileResult, LoginResult, LogoutResult, OfflineProfile,
    OfflineProfilesResult, OpenProfileResult, RegisterResult,
};

#[derive(Default)]
struct AuthState {
    profile_directory_id: Option<String>,
    access_token: Option<Zeroizing<String>>,
    masked_identifier: Option<String>,
}

pub struct AppState {
    backend: RwLock<Option<Arc<ApiClient>>>,
    auth: RwLock<AuthState>,
    pub supervisor: SidecarSupervisor,
    pub store: LocalStore,
    pub keyring: SecureKeyring,
    pub device_id: Uuid,
    pub sidecar_executable: PathBuf,
    pub app_version: String,
    pub development_mode: bool,
}

impl AppState {
    pub fn new(
        store: LocalStore,
        device_id: Uuid,
        sidecar_executable: PathBuf,
        app_version: String,
        development_mode: bool,
    ) -> Self {
        Self {
            backend: RwLock::new(None),
            auth: RwLock::new(AuthState::default()),
            supervisor: SidecarSupervisor::new(),
            store,
            keyring: SecureKeyring::new(),
            device_id,
            sidecar_executable,
            app_version,
            development_mode,
        }
    }

    async fn backend(&self) -> Result<Arc<ApiClient>, AppError> {
        self.backend
            .read()
            .await
            .as_ref()
            .cloned()
            .ok_or_else(|| AppError::Validation("Backend Origin is not validated".to_owned()))
    }
}

#[tauri::command]
pub async fn backend_validate_origin(
    state: State<'_, AppState>,
    origin: String,
) -> Result<BackendValidation, AppError> {
    let client = Arc::new(ApiClient::new(&origin, state.development_mode)?);
    client.ready().await?;
    let canonical_origin = client.canonical_origin();
    *state.backend.write().await = Some(client);
    Ok(BackendValidation {
        canonical_origin,
        ready: true,
    })
}

#[tauri::command]
pub async fn auth_register(
    state: State<'_, AppState>,
    email: String,
    password: String,
) -> Result<RegisterResult, AppError> {
    let result = state.backend().await?.register(&email, &password).await?;
    let registered_email = result
        .user
        .email
        .ok_or_else(|| AppError::Auth("Backend omitted the registered email".to_owned()))?;
    Ok(RegisterResult {
        app_user_id: result.user.id.to_string(),
        email: registered_email,
        masked_identifier: result.user.masked_identifier,
    })
}

#[tauri::command]
pub async fn auth_login(
    state: State<'_, AppState>,
    email: String,
    password: String,
) -> Result<LoginResult, AppError> {
    let backend = state.backend().await?;
    let session = backend.login(&email, &password, state.device_id).await?;
    let masked_identifier = session.user.masked_identifier.clone();
    if session.pwd_change_required {
        let mut auth = state.auth.write().await;
        auth.access_token = Some(Zeroizing::new(session.access_token));
        auth.masked_identifier = Some(masked_identifier.clone());
        auth.profile_directory_id = None;
        return Ok(LoginResult {
            status: "password_change_required".to_owned(),
            profile_directory_id: None,
            masked_identifier,
            catalog_release_sequence: None,
        });
    }
    open_online_session(&state, &backend, session).await
}

#[tauri::command]
pub async fn auth_change_password(
    state: State<'_, AppState>,
    current_password: String,
    new_password: String,
) -> Result<LoginResult, AppError> {
    let backend = state.backend().await?;
    let access_token = state
        .auth
        .read()
        .await
        .access_token
        .as_ref()
        .map(|token| token.to_string())
        .ok_or_else(|| AppError::Auth("No restricted password session".to_owned()))?;
    let session = backend
        .change_password(&access_token, &current_password, &new_password)
        .await?;
    open_online_session(&state, &backend, session).await
}

#[tauri::command]
pub async fn auth_close_profile(
    state: State<'_, AppState>,
) -> Result<CloseProfileResult, AppError> {
    let closed = state.supervisor.stop().await?;
    let mut auth = state.auth.write().await;
    auth.access_token = None;
    auth.profile_directory_id = None;
    auth.masked_identifier = None;
    Ok(CloseProfileResult {
        closed_profile: closed,
    })
}

#[tauri::command]
pub async fn auth_list_offline_profiles(
    state: State<'_, AppState>,
) -> Result<OfflineProfilesResult, AppError> {
    let mut profiles = Vec::new();
    for meta in state.store.list_profile_meta()? {
        let bundle = match state.keyring.load_bundle(&meta.profile_directory_id) {
            Ok(Some(value)) if value.schema_version == 1 => value,
            _ => continue,
        };
        let catalog_keyset = match load_catalog_keyset(&state, &meta.profile_directory_id) {
            Ok(value) => value,
            Err(_) => continue,
        };
        let catalog_keys =
            match verify_catalog_keyset(&catalog_keyset, state.development_mode, true) {
                Ok(value) => value,
                Err(_) => continue,
            };
        let auth_keyset = match load_auth_keyset(&state, &meta.profile_directory_id) {
            Ok(value) => value,
            Err(_) => continue,
        };
        if verify_auth_keyset(&auth_keyset, &catalog_keys, true).is_err() {
            continue;
        }
        let expires_at = match verify_offline_ticket(
            &bundle.offline_session_ticket,
            &auth_keyset,
            &meta.backend_origin,
            meta.app_user_id,
            state.device_id,
        ) {
            Ok(value) => value,
            Err(_) => continue,
        };
        profiles.push(OfflineProfile {
            profile_directory_id: meta.profile_directory_id,
            backend_origin: meta.backend_origin,
            masked_identifier: meta.masked_identifier,
            expires_at: expires_at.to_rfc3339_opts(SecondsFormat::Secs, true),
        });
    }
    Ok(OfflineProfilesResult { profiles })
}

#[tauri::command]
pub async fn auth_open_profile(
    state: State<'_, AppState>,
    profile_directory_id: String,
) -> Result<OpenProfileResult, AppError> {
    let meta = state
        .store
        .list_profile_meta()?
        .into_iter()
        .find(|candidate| candidate.profile_directory_id == profile_directory_id)
        .ok_or_else(|| AppError::NotFound("Offline Profile is unavailable".to_owned()))?;
    let bundle = state
        .keyring
        .load_bundle(&profile_directory_id)?
        .filter(|value| value.schema_version == 1)
        .ok_or_else(|| AppError::Security("KEYCHAIN_BUNDLE_CORRUPT".to_owned()))?;
    let backend = Arc::new(ApiClient::new(
        &meta.backend_origin,
        state.development_mode,
    )?);
    match backend.ready().await {
        Ok(_) => {
            *state.backend.write().await = Some(backend.clone());
            let session = backend.refresh(&bundle.refresh_token).await?;
            let login = open_online_session(&state, &backend, session).await?;
            Ok(OpenProfileResult {
                profile_directory_id: login
                    .profile_directory_id
                    .ok_or_else(|| AppError::Internal("Online Profile did not open".to_owned()))?,
                mode: "online".to_owned(),
                catalog_release_sequence: login.catalog_release_sequence.ok_or_else(|| {
                    AppError::Internal("Catalog release is unavailable".to_owned())
                })?,
            })
        }
        Err(AppError::Network(_)) => open_offline_session(&state, &meta, &bundle).await,
        Err(error) => Err(error),
    }
}

#[tauri::command]
pub async fn auth_logout(state: State<'_, AppState>) -> Result<LogoutResult, AppError> {
    let closed_profile = state.supervisor.stop().await?;
    let (access_token, profile_id) = {
        let mut auth = state.auth.write().await;
        let result = (
            auth.access_token.take().map(|value| value.to_string()),
            auth.profile_directory_id.take(),
        );
        auth.masked_identifier = None;
        result
    };
    let revoked_family = match (access_token, state.backend.read().await.as_ref().cloned()) {
        (Some(access_token), Some(backend)) => backend.logout(&access_token).await.is_ok(),
        _ => false,
    };
    if let Some(profile_id) = profile_id {
        state.keyring.delete_bundle(&profile_id)?;
    }
    Ok(LogoutResult {
        closed_profile,
        revoked_family,
    })
}

#[tauri::command]
pub async fn rpc_request(
    state: State<'_, AppState>,
    method: String,
    params: Value,
    idempotency_key: Option<String>,
) -> Result<Value, AppError> {
    let is_write = sidecar_method_kind(&method)?;
    let key = match (is_write, idempotency_key) {
        (true, Some(value)) => Some(
            Uuid::parse_str(&value)
                .map_err(|_| AppError::Validation("Invalid idempotency key".to_owned()))?,
        ),
        (true, None) => {
            return Err(AppError::Validation(
                "A write RPC requires an idempotency key".to_owned(),
            ))
        }
        (false, None) => None,
        (false, Some(_)) => {
            return Err(AppError::Validation(
                "A read RPC must not use an idempotency key".to_owned(),
            ))
        }
    };
    state
        .supervisor
        .client()
        .await?
        .call(&method, params, key)
        .await
}

async fn open_online_session(
    state: &State<'_, AppState>,
    backend: &Arc<ApiClient>,
    session: crate::rpc::api_client::SessionData,
) -> Result<LoginResult, AppError> {
    let refresh_token = session
        .refresh_token
        .clone()
        .ok_or_else(|| AppError::Auth("Backend omitted Refresh Token".to_owned()))?;
    let _refresh_seconds = session
        .refresh_token_expires_in
        .ok_or_else(|| AppError::Auth("Backend omitted Refresh Token expiry".to_owned()))?;
    let offline_ticket = session
        .offline_session_ticket
        .clone()
        .ok_or_else(|| AppError::Auth("Backend omitted OfflineSessionTicket".to_owned()))?;
    let _offline_seconds = session
        .offline_session_ticket_expires_in
        .ok_or_else(|| AppError::Auth("Backend omitted OfflineSessionTicket expiry".to_owned()))?;
    let catalog_keyset = backend.catalog_keys().await?;
    let catalog_keys = verify_catalog_keyset(&catalog_keyset, state.development_mode, false)?;
    let auth_keyset = backend.auth_keys().await?;
    verify_auth_keyset(&auth_keyset, &catalog_keys, false)?;
    let origin = backend.canonical_origin();
    verify_offline_ticket(
        &offline_ticket,
        &auth_keyset,
        &origin,
        session.user.id,
        state.device_id,
    )?;
    let manifest = backend.latest_catalog_manifest().await?;
    let profile_id = profile_directory_id(&origin, session.user.id);
    let profile_root = state.store.profile_path(&profile_id)?;
    std::fs::create_dir_all(&profile_root).map_err(|error| AppError::Storage(error.to_string()))?;
    let now = Utc::now();
    let bundle = SessionBundle {
        schema_version: 1,
        refresh_token,
        offline_session_ticket: offline_ticket,
        family_id: session.family_id.to_string(),
        issued_at: now.to_rfc3339_opts(SecondsFormat::Secs, true),
    };
    state.keyring.store_bundle(&profile_id, &bundle)?;
    write_profile_json(
        &state.store,
        &profile_id,
        "catalog-keyset.v1.json",
        &catalog_keyset,
    )?;
    write_profile_json(
        &state.store,
        &profile_id,
        "auth-keyset.v1.json",
        &auth_keyset,
    )?;
    write_profile_json(
        &state.store,
        &profile_id,
        "catalog-manifest.v1.json",
        &manifest,
    )?;
    state.store.write_profile_meta(&ProfileMeta {
        schema_version: 1,
        profile_directory_id: profile_id.clone(),
        backend_origin: origin.clone(),
        app_user_id: session.user.id,
        masked_identifier: session.user.masked_identifier.clone(),
    })?;
    state
        .supervisor
        .start(
            &state.sidecar_executable,
            &state.store.runtime_path(),
            &profile_root,
            &state.app_version,
            SidecarProfile {
                backend_origin: &origin,
                app_user_id: session.user.id,
                masked_identifier: &session.user.masked_identifier,
                device_id: state.device_id,
                mode: "online",
            },
        )
        .await?;
    let masked_identifier = session.user.masked_identifier;
    let mut auth = state.auth.write().await;
    auth.profile_directory_id = Some(profile_id.clone());
    auth.access_token = Some(Zeroizing::new(session.access_token));
    auth.masked_identifier = Some(masked_identifier.clone());
    Ok(LoginResult {
        status: "profile_opened".to_owned(),
        profile_directory_id: Some(profile_id),
        masked_identifier,
        catalog_release_sequence: Some(manifest.release_sequence),
    })
}

async fn open_offline_session(
    state: &State<'_, AppState>,
    meta: &ProfileMeta,
    bundle: &SessionBundle,
) -> Result<OpenProfileResult, AppError> {
    let catalog_keyset = load_catalog_keyset(state, &meta.profile_directory_id)?;
    let catalog_keys = verify_catalog_keyset(&catalog_keyset, state.development_mode, true)?;
    let auth_keyset = load_auth_keyset(state, &meta.profile_directory_id)?;
    verify_auth_keyset(&auth_keyset, &catalog_keys, true)?;
    verify_offline_ticket(
        &bundle.offline_session_ticket,
        &auth_keyset,
        &meta.backend_origin,
        meta.app_user_id,
        state.device_id,
    )?;
    let manifest: crate::rpc::api_client::CatalogManifest = read_profile_json(
        &state.store,
        &meta.profile_directory_id,
        "catalog-manifest.v1.json",
    )?;
    let profile_root = state.store.profile_path(&meta.profile_directory_id)?;
    state
        .supervisor
        .start(
            &state.sidecar_executable,
            &state.store.runtime_path(),
            &profile_root,
            &state.app_version,
            SidecarProfile {
                backend_origin: &meta.backend_origin,
                app_user_id: meta.app_user_id,
                masked_identifier: &meta.masked_identifier,
                device_id: state.device_id,
                mode: "offline",
            },
        )
        .await?;
    let mut auth = state.auth.write().await;
    auth.profile_directory_id = Some(meta.profile_directory_id.clone());
    auth.access_token = None;
    auth.masked_identifier = Some(meta.masked_identifier.clone());
    Ok(OpenProfileResult {
        profile_directory_id: meta.profile_directory_id.clone(),
        mode: "offline".to_owned(),
        catalog_release_sequence: manifest.release_sequence,
    })
}

fn write_profile_json<T: serde::Serialize>(
    store: &LocalStore,
    profile_directory_id: &str,
    name: &str,
    value: &T,
) -> Result<(), AppError> {
    let bytes = serde_json::to_vec(value).map_err(|error| AppError::Internal(error.to_string()))?;
    store.write_profile_document(profile_directory_id, name, &bytes)
}

fn read_profile_json<T: serde::de::DeserializeOwned>(
    store: &LocalStore,
    profile_directory_id: &str,
    name: &str,
) -> Result<T, AppError> {
    serde_json::from_slice(&store.read_profile_document(profile_directory_id, name)?)
        .map_err(|_| AppError::Security(format!("{name} is corrupt")))
}

fn load_catalog_keyset(
    state: &State<'_, AppState>,
    profile_directory_id: &str,
) -> Result<crate::rpc::api_client::CatalogKeyset, AppError> {
    read_profile_json(&state.store, profile_directory_id, "catalog-keyset.v1.json")
}

fn load_auth_keyset(
    state: &State<'_, AppState>,
    profile_directory_id: &str,
) -> Result<crate::rpc::api_client::AuthKeyset, AppError> {
    read_profile_json(&state.store, profile_directory_id, "auth-keyset.v1.json")
}

fn sidecar_method_kind(method: &str) -> Result<bool, AppError> {
    let write = matches!(
        method,
        "company.create"
            | "company.update"
            | "company.archive"
            | "department.create"
            | "department.update"
            | "department.archive"
            | "department.setLeader"
            | "department.responsibility.create"
            | "department.responsibility.update"
            | "department.responsibility.delete"
            | "employee.create"
            | "employee.updateStatus"
            | "employee.updateDisplayName"
            | "employee.updateBaseProfile"
            | "employee.transfer"
            | "profile.createDraft"
            | "profile.updateDraft"
            | "profile.bindSkill"
            | "profile.unbindSkill"
            | "profile.validate"
            | "profile.publish"
            | "profile.retireVersion"
            | "profile.retire"
            | "conversation.submitUserMessage"
            | "task.confirmPlan"
            | "task.requestPlanRevision"
            | "task.rejectPlan"
            | "task.pause"
            | "task.resume"
            | "task.cancel"
            | "departmentTask.checkResources"
            | "departmentTask.replaceEmployee"
            | "runtime.probeAgent"
            | "runtime.probeProvider"
            | "run.cancel"
            | "run.resume"
            | "approval.resolve"
            | "workspace.apply"
            | "workspace.abandon"
            | "workspace.cleanupTask"
            | "review.submit"
            | "review.rerun"
            | "review.resolveIssue"
            | "catalog.sync"
            | "catalog.installSkill"
            | "catalog.removeSkill"
            | "catalog.verifyCache"
            | "knowledge.import"
            | "knowledge.remove"
            | "backup.create"
            | "backup.restore"
            | "settings.update"
    );
    let read = matches!(
        method,
        "company.get"
            | "company.list"
            | "department.get"
            | "department.list"
            | "employee.get"
            | "employee.list"
            | "profile.get"
            | "profile.list"
            | "conversation.getCompany"
            | "conversation.getDepartment"
            | "conversation.listMessages"
            | "task.get"
            | "task.list"
            | "task.getGraph"
            | "task.getEvidence"
            | "departmentTask.getReport"
            | "runtime.listAvailableModels"
            | "runtime.getStatus"
            | "run.get"
            | "run.list"
            | "run.listEvents"
            | "approval.listPending"
            | "artifact.list"
            | "artifact.getSnapshot"
            | "workspace.get"
            | "review.listIssues"
            | "catalog.getActiveRelease"
            | "catalog.listAgents"
            | "catalog.listModels"
            | "catalog.listSkills"
            | "knowledge.list"
            | "knowledge.search"
            | "backup.list"
            | "settings.get"
            | "event.subscribe"
            | "event.replay"
    );
    if write {
        Ok(true)
    } else if read {
        Ok(false)
    } else {
        Err(AppError::Validation("METHOD_NOT_ALLOWED".to_owned()))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn profile_id_is_stable_and_path_safe() {
        let user_id = Uuid::parse_str("00000000-0000-4000-8000-000000000001").expect("valid UUID");
        let first = profile_directory_id("https://example.com:443", user_id);
        let second = profile_directory_id("https://example.com:443", user_id);
        assert_eq!(first, second);
        assert_eq!(first.len(), 52);
        assert!(first
            .bytes()
            .all(|value| { value.is_ascii_lowercase() || value.is_ascii_digit() }));
    }

    #[test]
    fn rpc_ownership_rejects_rust_and_supervisor_methods() {
        for method in ["auth.login", "backend.validateOrigin", "system.shutdown"] {
            assert!(sidecar_method_kind(method).is_err(), "{method}");
        }
        assert!(!sidecar_method_kind("company.list").expect("read"));
        assert!(sidecar_method_kind("company.create").expect("write"));
    }
}
