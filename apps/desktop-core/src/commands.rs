//! Tauri command boundary. Rust-owned methods never enter the Sidecar.

pub mod diagnostics;
pub mod external;
pub mod updater;
pub mod workspace;

pub use diagnostics::*;
pub use external::*;
pub use updater::{updater_check, updater_install, updater_restore_stable, updater_verify_launch};
pub use workspace::*;

use std::collections::BTreeSet;
use std::path::PathBuf;
use std::sync::Arc;

use chrono::{SecondsFormat, Utc};
use serde_json::Value;
use tauri::State;
use tokio::sync::RwLock;
use tracing::{error, info, instrument, warn};
use uuid::Uuid;
use zeroize::Zeroizing;

use crate::broker::credential::CredentialStore;
use crate::broker::dns_policy::DnsPolicy;
use crate::broker::domain_policy::NormalizedDomain;
use crate::broker::egress::EgressBroker;
use crate::broker::http::HttpBroker;
use crate::broker::http_stream::HttpStreamManager;
use crate::broker::lease::CredentialLeaseManager;
use crate::error::AppError;
use crate::ipc::dispatcher::ReverseMethodTable;
use crate::keyring::{SecureKeyring, SessionBundle};
use crate::process::{AgentReleasePolicy, AgentType, AgentVersionRangePolicy, ProcessSupervisor};
use crate::rpc::api_client::{ApiClient, CatalogManifest};
use crate::rpc::reverse::{
    register_reverse_handlers, CatalogAgentBinding, CatalogAgentVersionRange, CatalogModelBinding,
    CatalogProviderBinding, CatalogSnapshot, ProviderProtocol, ReverseBroker,
};
use crate::security::external_write::ReceiptStore;
use crate::security::grant_store::GrantStore;
use crate::sidecar::{SidecarProfile, SidecarSupervisor};
use crate::store::{profile_directory_id, LocalStore, ProfileMeta};
use crate::trust::{
    verify_auth_keyset, verify_catalog_keyset, verify_catalog_manifest, verify_offline_ticket,
};
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
    pub grant_store: Arc<GrantStore>,
    pub receipt_store: Arc<ReceiptStore>,
    pub device_id: Uuid,
    pub sidecar_executable: PathBuf,
    pub app_version: String,
    pub development_mode: bool,
    pub http_broker: Arc<HttpBroker>,
    pub egress_broker: Arc<EgressBroker>,
    pub credential_store: Arc<CredentialStore>,
    pub reverse_table: Arc<ReverseMethodTable>,
    pub process_supervisor: Arc<ProcessSupervisor>,
    pub reverse_broker: Arc<ReverseBroker>,
}

impl AppState {
    pub fn new(
        store: LocalStore,
        device_id: Uuid,
        sidecar_executable: PathBuf,
        app_version: String,
        development_mode: bool,
    ) -> Self {
        let credential_store = Arc::new(CredentialStore::new());
        let dns_policy = Arc::new(DnsPolicy::new());
        let stream_manager = Arc::new(HttpStreamManager::new());
        let lease_manager = Arc::new(CredentialLeaseManager::new(300));
        let egress_broker = Arc::new(EgressBroker::new());
        let http_broker = Arc::new(HttpBroker::new(
            credential_store.clone(),
            dns_policy,
            stream_manager,
            lease_manager,
            egress_broker.clone(),
        ));
        let mut reverse_table = ReverseMethodTable::new();
        let grant_store = Arc::new(GrantStore::new());
        let receipt_store = Arc::new(ReceiptStore::new());
        let process_supervisor = Arc::new(ProcessSupervisor::with_grant_store(
            egress_broker.clone(),
            grant_store.clone(),
        ));
        let reverse_broker = register_reverse_handlers(
            &mut reverse_table,
            http_broker.clone(),
            credential_store.clone(),
            grant_store.clone(),
            receipt_store.clone(),
            process_supervisor.clone(),
        );
        let rev_table_arc = Arc::new(reverse_table);
        Self {
            backend: RwLock::new(None),
            auth: RwLock::new(AuthState::default()),
            supervisor: SidecarSupervisor::new(rev_table_arc.clone()),
            store,
            keyring: SecureKeyring::new(),
            grant_store,
            receipt_store,
            device_id,
            sidecar_executable,
            app_version,
            development_mode,
            http_broker,
            credential_store,
            egress_broker,
            reverse_table: rev_table_arc.clone(),
            process_supervisor,
            reverse_broker,
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

#[instrument(skip(state), fields(command = "backend_validate_origin"))]
pub async fn backend_validate_origin_impl(
    state: &AppState,
    origin: String,
) -> Result<BackendValidation, AppError> {
    info!(origin = %origin, "command.backend_validate_origin.start");
    let start = std::time::Instant::now();
    let client = Arc::new(ApiClient::new(&origin, state.development_mode)?);
    client.ready().await?;
    let canonical_origin = client.canonical_origin();
    *state.backend.write().await = Some(client);
    let elapsed = start.elapsed().as_millis();
    info!(origin = %origin, elapsed_ms = elapsed, "command.backend_validate_origin.completed");
    Ok(BackendValidation {
        canonical_origin,
        ready: true,
    })
}

#[tauri::command]
pub async fn backend_validate_origin(
    state: State<'_, AppState>,
    origin: String,
) -> Result<BackendValidation, AppError> {
    backend_validate_origin_impl(state.inner(), origin).await
}

#[instrument(skip(state), fields(command = "auth_register"))]
pub async fn auth_register_impl(
    state: &AppState,
    email: String,
    password: String,
) -> Result<RegisterResult, AppError> {
    info!(email = %email, "command.auth_register.start");
    let start = std::time::Instant::now();
    let result = state.backend().await?.register(&email, &password).await?;
    let registered_email = result
        .user
        .email
        .ok_or_else(|| AppError::Auth("Backend omitted the registered email".to_owned()))?;
    let elapsed = start.elapsed().as_millis();
    info!(elapsed_ms = elapsed, "command.auth_register.completed");
    Ok(RegisterResult {
        app_user_id: result.user.id.to_string(),
        email: registered_email,
        masked_identifier: result.user.masked_identifier,
    })
}

#[tauri::command]
pub async fn auth_register(
    state: State<'_, AppState>,
    email: String,
    password: String,
) -> Result<RegisterResult, AppError> {
    auth_register_impl(state.inner(), email, password).await
}

#[instrument(skip(state), fields(command = "auth_login"))]
pub async fn auth_login_impl(
    state: &AppState,
    email: String,
    password: String,
) -> Result<LoginResult, AppError> {
    info!(email = %email, "command.auth_login.start");
    let start = std::time::Instant::now();
    let backend = state.backend().await?;
    let session = backend.login(&email, &password, state.device_id).await?;
    let masked_identifier = session.user.masked_identifier.clone();
    if session.pwd_change_required {
        state.grant_store.clear().await;
        state.receipt_store.clear().await;
        let mut auth = state.auth.write().await;
        auth.access_token = Some(Zeroizing::new(session.access_token));
        auth.masked_identifier = Some(masked_identifier.clone());
        auth.profile_directory_id = None;
        info!(
            elapsed_ms = start.elapsed().as_millis(),
            "command.auth_login.password_change_required"
        );
        return Ok(LoginResult {
            status: "password_change_required".to_owned(),
            profile_directory_id: None,
            masked_identifier,
            catalog_release_sequence: None,
        });
    }
    let result = open_online_session(state, &backend, session).await;
    let elapsed = start.elapsed().as_millis();
    match &result {
        Ok(_) => info!(elapsed_ms = elapsed, "command.auth_login.completed"),
        Err(e) => error!(error = %e, elapsed_ms = elapsed, "command.auth_login.failed"),
    }
    result
}

#[tauri::command]
pub async fn auth_login(
    state: State<'_, AppState>,
    email: String,
    password: String,
) -> Result<LoginResult, AppError> {
    auth_login_impl(state.inner(), email, password).await
}

#[instrument(skip(state), fields(command = "auth_change_password"))]
pub async fn auth_change_password_impl(
    state: &AppState,
    current_password: String,
    new_password: String,
) -> Result<LoginResult, AppError> {
    info!("command.auth_change_password.start");
    let start = std::time::Instant::now();
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
    let result = open_online_session(state, &backend, session).await;
    let elapsed = start.elapsed().as_millis();
    match &result {
        Ok(_) => info!(
            elapsed_ms = elapsed,
            "command.auth_change_password.completed"
        ),
        Err(e) => error!(error = %e, elapsed_ms = elapsed, "command.auth_change_password.failed"),
    }
    result
}

#[tauri::command]
pub async fn auth_change_password(
    state: State<'_, AppState>,
    current_password: String,
    new_password: String,
) -> Result<LoginResult, AppError> {
    auth_change_password_impl(state.inner(), current_password, new_password).await
}

#[instrument(skip(state), fields(command = "auth_close_profile"))]
pub async fn auth_close_profile_impl(state: &AppState) -> Result<CloseProfileResult, AppError> {
    info!("command.auth_close_profile.start");
    let closed = state.supervisor.stop().await?;
    state.process_supervisor.reset().await;
    state.grant_store.clear().await;
    state.receipt_store.clear().await;
    state.process_supervisor.bind_client(None).await;
    state.reverse_broker.bind_client(None).await;
    state.reverse_broker.bind_profile(None).await;
    state.reverse_broker.bind_catalog(None).await;
    let mut auth = state.auth.write().await;
    auth.access_token = None;
    auth.profile_directory_id = None;
    auth.masked_identifier = None;
    info!(closed = closed, "command.auth_close_profile.completed");
    Ok(CloseProfileResult {
        closed_profile: closed,
    })
}

#[tauri::command]
pub async fn auth_close_profile(
    state: State<'_, AppState>,
) -> Result<CloseProfileResult, AppError> {
    auth_close_profile_impl(state.inner()).await
}

#[instrument(skip(state), fields(command = "auth_list_offline_profiles"))]
pub async fn auth_list_offline_profiles_impl(
    state: &AppState,
) -> Result<OfflineProfilesResult, AppError> {
    info!("command.auth_list_offline_profiles.start");
    let mut profiles = Vec::new();
    for meta in state.store.list_profile_meta()? {
        let bundle = match state.keyring.load_bundle(&meta.profile_directory_id) {
            Ok(Some(value)) if value.schema_version == 1 => value,
            _ => continue,
        };
        let catalog_keyset = match load_catalog_keyset(state, &meta.profile_directory_id) {
            Ok(value) => value,
            Err(_) => continue,
        };
        let catalog_keys =
            match verify_catalog_keyset(&catalog_keyset, state.development_mode, true) {
                Ok(value) => value,
                Err(_) => continue,
            };
        let auth_keyset = match load_auth_keyset(state, &meta.profile_directory_id) {
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
    info!(
        count = profiles.len(),
        "command.auth_list_offline_profiles.completed"
    );
    Ok(OfflineProfilesResult { profiles })
}

#[tauri::command]
pub async fn auth_list_offline_profiles(
    state: State<'_, AppState>,
) -> Result<OfflineProfilesResult, AppError> {
    auth_list_offline_profiles_impl(state.inner()).await
}

#[instrument(skip(state), fields(command = "auth_open_profile"))]
pub async fn auth_open_profile_impl(
    state: &AppState,
    profile_directory_id: String,
) -> Result<OpenProfileResult, AppError> {
    info!(profile_id = %profile_directory_id, "command.auth_open_profile.start");
    let start = std::time::Instant::now();
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
            info!(profile_id = %profile_directory_id, mode = "online", "command.auth_open_profile.backend_ready");
            *state.backend.write().await = Some(backend.clone());
            let session = backend.refresh(&bundle.refresh_token).await?;
            let login = open_online_session(state, &backend, session).await?;
            let elapsed = start.elapsed().as_millis();
            info!(elapsed_ms = elapsed, "command.auth_open_profile.completed");
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
        Err(AppError::Network(_)) => {
            warn!(profile_id = %profile_directory_id, "command.auth_open_profile.offline_fallback");
            let result = open_offline_session(state, &meta, &bundle).await;
            let elapsed = start.elapsed().as_millis();
            match &result {
                Ok(_) => info!(
                    elapsed_ms = elapsed,
                    mode = "offline",
                    "command.auth_open_profile.completed"
                ),
                Err(e) => {
                    error!(error = %e, elapsed_ms = elapsed, "command.auth_open_profile.failed")
                }
            }
            result
        }
        Err(error) => {
            error!(error = %error, "command.auth_open_profile.backend_unreachable");
            Err(error)
        }
    }
}

#[tauri::command]
pub async fn auth_open_profile(
    state: State<'_, AppState>,
    profile_directory_id: String,
) -> Result<OpenProfileResult, AppError> {
    auth_open_profile_impl(state.inner(), profile_directory_id).await
}

#[instrument(skip(state), fields(command = "auth_logout"))]
pub async fn auth_logout_impl(state: &AppState) -> Result<LogoutResult, AppError> {
    info!("command.auth_logout.start");
    let closed_profile = state.supervisor.stop().await?;
    state.process_supervisor.reset().await;
    state.grant_store.clear().await;
    state.receipt_store.clear().await;
    state.process_supervisor.bind_client(None).await;
    state.reverse_broker.bind_client(None).await;
    state.reverse_broker.bind_profile(None).await;
    state.reverse_broker.bind_catalog(None).await;
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
    if let Some(ref profile_id) = profile_id {
        state.keyring.delete_bundle(profile_id)?;
    }
    info!(revoked = revoked_family, "command.auth_logout.completed");
    Ok(LogoutResult {
        closed_profile,
        revoked_family,
    })
}

#[tauri::command]
pub async fn auth_logout(state: State<'_, AppState>) -> Result<LogoutResult, AppError> {
    auth_logout_impl(state.inner()).await
}

#[instrument(skip(state), fields(command = "rpc_request"))]
#[tauri::command]
pub async fn rpc_request(
    state: State<'_, AppState>,
    method: String,
    params: Value,
    idempotency_key: Option<String>,
) -> Result<Value, AppError> {
    info!(method = %method, "command.rpc_request.start");
    let start = std::time::Instant::now();
    if method == "system.health"
        || method == "updater.verifyLaunch"
        || method == "updater.restoreStable"
    {
        let is_write = method == "updater.restoreStable";
        match (is_write, idempotency_key) {
            (false, None) => {}
            (true, Some(value)) => {
                Uuid::parse_str(&value)
                    .map_err(|_| AppError::Validation("Invalid idempotency key".to_owned()))?;
            }
            (true, None) => {
                return Err(AppError::Validation(
                    "A write RPC requires an idempotency key".to_owned(),
                ));
            }
            (false, Some(_)) => {
                return Err(AppError::Validation(
                    "A read RPC must not use an idempotency key".to_owned(),
                ));
            }
        }
        return dispatch_rust_core(state.inner(), &method, params).await;
    }
    let sidecar_kind = crate::rpc::generated_method_kinds::sidecar_method_kind(&method);
    let owner_kind = crate::rpc::generated_method_kinds::rust_core_method_kind(&method);
    let is_write = match (sidecar_kind, owner_kind) {
        (Some(kind), None) => kind,
        (None, Some(kind)) => kind,
        _ => return Err(AppError::Validation("METHOD_NOT_ALLOWED".to_owned())),
    };
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
    let result = if owner_kind.is_some() {
        dispatch_rust_core(state.inner(), &method, params).await
    } else {
        state
            .supervisor
            .client()
            .await?
            .call(&method, params, key)
            .await
    };
    let elapsed = start.elapsed().as_millis();
    match &result {
        Ok(_) => info!(method = %method, elapsed_ms = elapsed, "command.rpc_request.completed"),
        Err(e) => {
            error!(method = %method, error = %e, elapsed_ms = elapsed, "command.rpc_request.failed")
        }
    }
    result
}

async fn dispatch_rust_core(
    state: &AppState,
    method: &str,
    params: Value,
) -> Result<Value, AppError> {
    let object = params
        .as_object()
        .ok_or_else(|| AppError::Validation("RPC_PARAMS_INVALID".to_owned()))?;
    let string_param = |name: &str| {
        object
            .get(name)
            .and_then(Value::as_str)
            .filter(|value| !value.trim().is_empty())
            .map(str::to_owned)
            .ok_or_else(|| AppError::Validation(format!("RPC_PARAM_REQUIRED:{name}")))
    };
    match method {
        "backend.validateOrigin" => serde_json::to_value(
            backend_validate_origin_impl(state, string_param("origin")?).await?,
        )
        .map_err(|error| AppError::Internal(error.to_string())),
        "auth.register" => serde_json::to_value(
            auth_register_impl(state, string_param("email")?, string_param("password")?).await?,
        )
        .map_err(|error| AppError::Internal(error.to_string())),
        "auth.login" => serde_json::to_value(
            auth_login_impl(state, string_param("email")?, string_param("password")?).await?,
        )
        .map_err(|error| AppError::Internal(error.to_string())),
        "auth.changePassword" => serde_json::to_value(
            auth_change_password_impl(
                state,
                string_param("current_password")?,
                string_param("new_password")?,
            )
            .await?,
        )
        .map_err(|error| AppError::Internal(error.to_string())),
        "auth.logout" => serde_json::to_value(auth_logout_impl(state).await?)
            .map_err(|error| AppError::Internal(error.to_string())),
        "auth.listOfflineProfiles" => {
            serde_json::to_value(auth_list_offline_profiles_impl(state).await?)
                .map_err(|error| AppError::Internal(error.to_string()))
        }
        "auth.openProfile" => serde_json::to_value(
            auth_open_profile_impl(state, string_param("profile_directory_id")?).await?,
        )
        .map_err(|error| AppError::Internal(error.to_string())),
        "auth.closeProfile" => serde_json::to_value(auth_close_profile_impl(state).await?)
            .map_err(|error| AppError::Internal(error.to_string())),
        "system.health" => system_health_impl(state).await,
        "updater.verifyLaunch" => {
            serde_json::to_value(crate::commands::updater::updater_verify_launch_impl(state).await?)
                .map_err(|error| AppError::Internal(error.to_string()))
        }
        "updater.restoreStable" => serde_json::to_value(
            crate::commands::updater::updater_restore_stable_impl(state).await?,
        )
        .map_err(|error| AppError::Internal(error.to_string())),
        _ => Err(AppError::Validation("METHOD_NOT_ALLOWED".to_owned())),
    }
}

async fn open_online_session(
    state: &AppState,
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
    verify_catalog_manifest(&manifest, &catalog_keys)?;
    let catalog = load_catalog_snapshot(&manifest)?;
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
    write_profile_json(
        &state.store,
        &profile_id,
        "catalog-snapshot.v1.json",
        &catalog,
    )?;
    state.store.write_profile_meta(&ProfileMeta {
        schema_version: 1,
        profile_directory_id: profile_id.clone(),
        backend_origin: origin.clone(),
        app_user_id: session.user.id,
        masked_identifier: session.user.masked_identifier.clone(),
    })?;
    let (network_policy_sha256, network_domains) = catalog_network_policy(&catalog)?;
    // Validate and bind the signed catalog before mutating profile/session
    // bindings or spawning Sidecar. A bad catalog must leave no partial
    // runtime setup behind.
    bind_catalog_agents(&state.process_supervisor, &catalog).await?;
    state
        .reverse_broker
        .bind_profile(Some(profile_id.clone()))
        .await;
    state.process_supervisor.clear_network_policies().await;
    state
        .process_supervisor
        .bind_network_policy(network_policy_sha256, network_domains)
        .await;
    state
        .reverse_broker
        .bind_catalog(Some(catalog.clone()))
        .await;
    state
        .process_supervisor
        .bind_profile_root(Some(profile_root.clone()))
        .await?;
    state
        .grant_store
        .bind_profile_root(Some(profile_root.clone()))
        .await?;
    state
        .receipt_store
        .bind_profile_root(Some(profile_root.clone()))
        .await?;
    let sidecar_client = state
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
    let process_supervisor = Arc::clone(&state.process_supervisor);
    let reverse_broker = Arc::clone(&state.reverse_broker);
    sidecar_client
        .bind_disconnect_hook(Arc::new(move || {
            let process_supervisor = Arc::clone(&process_supervisor);
            let reverse_broker = Arc::clone(&reverse_broker);
            Box::pin(async move {
                process_supervisor.cancel_all("IPC_DISCONNECTED").await;
                reverse_broker.cancel_all().await;
            })
        }))
        .await;
    state
        .process_supervisor
        .bind_client(Some(sidecar_client))
        .await;
    if let Ok(client) = state.supervisor.client().await {
        state.reverse_broker.bind_client(Some(client)).await;
    }
    if let Err(error) = state.supervisor.check_health().await {
        let _ = state.supervisor.stop().await;
        state.process_supervisor.reset().await;
        state.reverse_broker.bind_client(None).await;
        return Err(error);
    }
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
    state: &AppState,
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
    verify_catalog_manifest(&manifest, &catalog_keys)?;
    let catalog: CatalogSnapshot = read_profile_json(
        &state.store,
        &meta.profile_directory_id,
        "catalog-snapshot.v1.json",
    )?;
    let profile_root = state.store.profile_path(&meta.profile_directory_id)?;
    let (network_policy_sha256, network_domains) = catalog_network_policy(&catalog)?;
    // Keep the offline path subject to the same signed-catalog validation as
    // the online path, and do it before profile/session mutation or Sidecar
    // startup for fail-closed setup.
    bind_catalog_agents(&state.process_supervisor, &catalog).await?;
    state
        .reverse_broker
        .bind_profile(Some(meta.profile_directory_id.clone()))
        .await;
    state.process_supervisor.clear_network_policies().await;
    state
        .process_supervisor
        .bind_network_policy(network_policy_sha256, network_domains)
        .await;
    state
        .reverse_broker
        .bind_catalog(Some(catalog.clone()))
        .await;
    state
        .process_supervisor
        .bind_profile_root(Some(profile_root.clone()))
        .await?;
    state
        .grant_store
        .bind_profile_root(Some(profile_root.clone()))
        .await?;
    state
        .receipt_store
        .bind_profile_root(Some(profile_root.clone()))
        .await?;
    let sidecar_client = state
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
    let process_supervisor = Arc::clone(&state.process_supervisor);
    let reverse_broker = Arc::clone(&state.reverse_broker);
    sidecar_client
        .bind_disconnect_hook(Arc::new(move || {
            let process_supervisor = Arc::clone(&process_supervisor);
            let reverse_broker = Arc::clone(&reverse_broker);
            Box::pin(async move {
                process_supervisor.cancel_all("IPC_DISCONNECTED").await;
                reverse_broker.cancel_all().await;
            })
        }))
        .await;
    state
        .process_supervisor
        .bind_client(Some(sidecar_client))
        .await;
    if let Ok(client) = state.supervisor.client().await {
        state.reverse_broker.bind_client(Some(client)).await;
    }
    if let Err(error) = state.supervisor.check_health().await {
        let _ = state.supervisor.stop().await;
        state.process_supervisor.reset().await;
        state.reverse_broker.bind_client(None).await;
        return Err(error);
    }
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

fn load_catalog_snapshot(manifest: &CatalogManifest) -> Result<CatalogSnapshot, AppError> {
    let mut agents = Vec::new();
    let mut snapshot = Vec::new();
    for resource in &manifest.resources {
        match resource.get("type").and_then(Value::as_str) {
            Some("agent") => {
                let agent_release_id = resource
                    .get("id")
                    .and_then(Value::as_str)
                    .and_then(|id| Uuid::parse_str(id).ok())
                    .ok_or_else(|| AppError::Security("CATALOG_AGENT_ID_INVALID".to_owned()))?;
                let key = resource
                    .get("key")
                    .and_then(Value::as_str)
                    .filter(|value| !value.trim().is_empty())
                    .ok_or_else(|| AppError::Security("CATALOG_AGENT_KEY_INVALID".to_owned()))?;
                if agent_type_for_key(key).is_none() {
                    return Err(AppError::Security("CATALOG_AGENT_TYPE_INVALID".to_owned()));
                }
                agents.push(CatalogAgentBinding {
                    agent_release_id,
                    key: key.to_owned(),
                    network_domains: resource
                        .get("network_domains")
                        .and_then(Value::as_array)
                        .map(|values| {
                            values
                                .iter()
                                .filter_map(Value::as_str)
                                .map(|value| value.trim().to_ascii_lowercase())
                                .filter(|value| !value.is_empty())
                                .collect()
                        })
                        .unwrap_or_default(),
                    version_ranges: parse_agent_version_ranges(resource)?,
                });
                continue;
            }
            Some("provider") => {}
            _ => continue,
        }
        let provider_release_id = resource
            .get("id")
            .and_then(Value::as_str)
            .and_then(|id| Uuid::parse_str(id).ok())
            .ok_or_else(|| AppError::Security("CATALOG_PROVIDER_ID_INVALID".to_owned()))?;
        let protocol_name = resource
            .get("protocol")
            .and_then(Value::as_str)
            .ok_or_else(|| AppError::Security("CATALOG_PROTOCOL_INVALID".to_owned()))?;
        let protocol = match protocol_name {
            "openai_responses" => ProviderProtocol::OpenaiResponses,
            "anthropic_messages" => ProviderProtocol::AnthropicMessages,
            "openai_chat_completions" => ProviderProtocol::OpenaiChatCompletions,
            _ => return Err(AppError::Security("CATALOG_PROTOCOL_INVALID".to_owned())),
        };
        let base_url_value = resource
            .get("base_url")
            .and_then(Value::as_str)
            .ok_or_else(|| AppError::Security("CATALOG_PROVIDER_URL_INVALID".to_owned()))?;
        let base_url = url::Url::parse(base_url_value)
            .map_err(|_| AppError::Security("CATALOG_PROVIDER_URL_INVALID".to_owned()))?;
        if base_url.scheme() != "https"
            || base_url.username() != ""
            || base_url.password().is_some()
            || base_url.query().is_some()
            || base_url.fragment().is_some()
            || base_url.host_str().is_none()
            || base_url.port().is_some_and(|port| port != 443)
        {
            return Err(AppError::Security(
                "CATALOG_PROVIDER_URL_INVALID".to_owned(),
            ));
        }
        let model_bindings_value = resource
            .get("model_bindings")
            .and_then(Value::as_array)
            .ok_or_else(|| AppError::Security("CATALOG_MODEL_BINDINGS_INVALID".to_owned()))?;
        let mut model_bindings = Vec::with_capacity(model_bindings_value.len());
        for binding in model_bindings_value {
            let binding_id = binding
                .get("binding_id")
                .and_then(Value::as_str)
                .and_then(|id| Uuid::parse_str(id).ok())
                .ok_or_else(|| AppError::Security("CATALOG_MODEL_BINDING_ID_INVALID".to_owned()))?;
            let model_id = binding
                .get("model_id")
                .and_then(Value::as_str)
                .and_then(|id| Uuid::parse_str(id).ok())
                .ok_or_else(|| AppError::Security("CATALOG_MODEL_ID_INVALID".to_owned()))?;
            let provider_model_name = binding
                .get("provider_model_name")
                .and_then(Value::as_str)
                .filter(|value| !value.trim().is_empty())
                .ok_or_else(|| AppError::Security("CATALOG_MODEL_NAME_INVALID".to_owned()))?;
            let request_defaults = binding
                .get("request_defaults")
                .cloned()
                .filter(Value::is_object)
                .ok_or_else(|| AppError::Security("CATALOG_REQUEST_DEFAULTS_INVALID".to_owned()))?;
            model_bindings.push(CatalogModelBinding {
                binding_id,
                model_id,
                provider_model_name: provider_model_name.to_owned(),
                request_defaults,
            });
        }
        snapshot.push(CatalogProviderBinding {
            provider_release_id,
            key: resource
                .get("key")
                .and_then(Value::as_str)
                .ok_or_else(|| AppError::Security("CATALOG_PROVIDER_KEY_INVALID".to_owned()))?
                .to_owned(),
            protocol,
            base_url: base_url_value.to_owned(),
            auth_scheme: resource
                .get("auth_scheme")
                .and_then(Value::as_str)
                .filter(|value| matches!(*value, "bearer" | "x-api-key"))
                .ok_or_else(|| AppError::Security("CATALOG_AUTH_SCHEME_INVALID".to_owned()))?
                .to_owned(),
            model_bindings,
        });
    }
    Ok(CatalogSnapshot {
        release_id: manifest.release_id,
        release_sequence: manifest.release_sequence,
        agents,
        providers: snapshot,
    })
}

async fn bind_catalog_agents(
    supervisor: &Arc<ProcessSupervisor>,
    catalog: &CatalogSnapshot,
) -> Result<(), AppError> {
    let mut policies = Vec::with_capacity(catalog.agents.len());
    for agent in &catalog.agents {
        let agent_type = agent_type_for_key(&agent.key)
            .ok_or_else(|| AppError::Security("CATALOG_AGENT_TYPE_INVALID".to_owned()))?;
        if agent.version_ranges.is_empty() {
            return Err(AppError::Security(
                "CATALOG_AGENT_VERSION_RANGES_INVALID".to_owned(),
            ));
        }
        let mut version_ranges = Vec::with_capacity(agent.version_ranges.len());
        for range in &agent.version_ranges {
            if range.min_version.trim().is_empty()
                || range.max_version_exclusive.trim().is_empty()
                || range.executable_names.is_empty()
                || range.supported_platforms.is_empty()
                || range.probe_argv.is_empty()
                || range.adapter_contract_version == 0
            {
                return Err(AppError::Security(
                    "CATALOG_AGENT_VERSION_RANGES_INVALID".to_owned(),
                ));
            }
            let min_version = semver::Version::parse(range.min_version.trim()).map_err(|_| {
                AppError::Security("CATALOG_AGENT_VERSION_RANGES_INVALID".to_owned())
            })?;
            let max_version_exclusive = semver::Version::parse(range.max_version_exclusive.trim())
                .map_err(|_| {
                    AppError::Security("CATALOG_AGENT_VERSION_RANGES_INVALID".to_owned())
                })?;
            if min_version >= max_version_exclusive
                || range
                    .executable_names
                    .iter()
                    .any(|name| name.trim().is_empty() || name.contains('/') || name.contains('\\'))
                || range
                    .supported_platforms
                    .iter()
                    .any(|platform| platform.trim().is_empty())
                || range
                    .probe_argv
                    .iter()
                    .any(|part| part.contains('\n') || part.contains('\r'))
            {
                return Err(AppError::Security(
                    "CATALOG_AGENT_VERSION_RANGES_INVALID".to_owned(),
                ));
            }
            version_ranges.push(AgentVersionRangePolicy {
                min_version,
                max_version_exclusive,
                executable_names: range
                    .executable_names
                    .iter()
                    .map(|name| name.trim().to_ascii_lowercase())
                    .collect(),
                supported_platforms: range
                    .supported_platforms
                    .iter()
                    .map(|platform| platform.trim().to_ascii_lowercase())
                    .collect(),
                probe_argv: range.probe_argv.clone(),
                adapter_contract_version: range.adapter_contract_version,
            });
        }
        policies.push((
            agent.agent_release_id,
            AgentReleasePolicy {
                agent_type,
                version_ranges,
                adapter_contract_version: 1,
            },
        ));
    }
    // A profile switch must invalidate every release from the previous
    // catalog only after the complete replacement catalog has validated.
    supervisor.clear_agent_releases().await;
    for (release_id, policy) in policies {
        supervisor
            .bind_agent_release_policy(release_id, policy)
            .await;
    }
    Ok(())
}

fn parse_agent_version_ranges(
    resource: &serde_json::Value,
) -> Result<Vec<CatalogAgentVersionRange>, AppError> {
    let values = resource
        .get("version_ranges")
        .and_then(Value::as_array)
        .ok_or_else(|| AppError::Security("CATALOG_AGENT_VERSION_RANGES_INVALID".to_owned()))?;
    values
        .iter()
        .map(|value| {
            serde_json::from_value(value.clone())
                .map_err(|_| AppError::Security("CATALOG_AGENT_VERSION_RANGES_INVALID".to_owned()))
        })
        .collect()
}

fn agent_type_for_key(key: &str) -> Option<AgentType> {
    match key.trim().to_ascii_lowercase().as_str() {
        "codex" | "codex_cli" => Some(AgentType::CodexCli),
        "claude" | "claude_code" => Some(AgentType::ClaudeCode),
        "opencode" => Some(AgentType::Opencode),
        _ => None,
    }
}

fn catalog_network_policy(
    catalog: &CatalogSnapshot,
) -> Result<(String, BTreeSet<NormalizedDomain>), AppError> {
    let mut domains = BTreeSet::new();
    for provider in &catalog.providers {
        let parsed = url::Url::parse(&provider.base_url)
            .map_err(|_| AppError::Security("CATALOG_PROVIDER_URL_INVALID".to_owned()))?;
        let host = parsed
            .host_str()
            .ok_or_else(|| AppError::Security("CATALOG_PROVIDER_HOST_REQUIRED".to_owned()))?;
        domains.insert(NormalizedDomain::new(host));
    }
    for agent in &catalog.agents {
        for domain in &agent.network_domains {
            domains.insert(NormalizedDomain::new(domain));
        }
    }
    let values: Vec<String> = domains
        .iter()
        .map(|value| value.as_str().to_owned())
        .collect();
    let encoded =
        serde_json::to_vec(&values).map_err(|error| AppError::Internal(error.to_string()))?;
    use sha2::{Digest, Sha256};
    let hash = Sha256::digest(encoded)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect();
    Ok((hash, domains))
}

fn read_profile_json<T: serde::de::DeserializeOwned>(
    store: &LocalStore,
    profile_directory_id: &str,
    name: &str,
) -> Result<T, AppError> {
    serde_json::from_slice(&store.read_profile_document(profile_directory_id, name)?)
        .map_err(|_| AppError::Security(format!("{name} is corrupt")))
}

pub(super) fn load_catalog_keyset(
    state: &AppState,
    profile_directory_id: &str,
) -> Result<crate::rpc::api_client::CatalogKeyset, AppError> {
    read_profile_json(&state.store, profile_directory_id, "catalog-keyset.v1.json")
}

fn load_auth_keyset(
    state: &AppState,
    profile_directory_id: &str,
) -> Result<crate::rpc::api_client::AuthKeyset, AppError> {
    read_profile_json(&state.store, profile_directory_id, "auth-keyset.v1.json")
}

pub async fn system_health_impl(state: &AppState) -> Result<serde_json::Value, AppError> {
    let (sidecar_running, sidecar_healthy) = if state.supervisor.is_running().await {
        (true, state.supervisor.check_health().await.is_ok())
    } else {
        (false, false)
    };

    let status = if sidecar_running && sidecar_healthy {
        "healthy"
    } else if sidecar_running {
        "degraded"
    } else {
        "unhealthy"
    };

    Ok(serde_json::json!({
        "status": status,
        "platform": std::env::consts::OS,
        "arch": std::env::consts::ARCH,
        "sidecar": {
            "running": sidecar_running,
            "healthy": sidecar_healthy,
        },
    }))
}

#[tauri::command]
pub async fn system_health(state: State<'_, AppState>) -> Result<serde_json::Value, AppError> {
    system_health_impl(state.inner()).await
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
    fn rpc_ownership_uses_generated_registry() {
        // auth methods are now rust_core owned, not in sidecar list
        assert!(crate::rpc::generated_method_kinds::sidecar_method_kind("auth.login").is_none());
        assert!(
            crate::rpc::generated_method_kinds::sidecar_method_kind("backend.validateOrigin")
                .is_none()
        );
        // system methods are not in the sidecar registry
        assert!(
            crate::rpc::generated_method_kinds::sidecar_method_kind("system.shutdown").is_none()
        );
        assert!(crate::rpc::generated_method_kinds::sidecar_method_kind("system.health").is_none());
        // known read/write from generated registry
        assert_eq!(
            crate::rpc::generated_method_kinds::sidecar_method_kind("company.list"),
            Some(false)
        );
        assert_eq!(
            crate::rpc::generated_method_kinds::sidecar_method_kind("company.create"),
            Some(true)
        );
        assert_eq!(
            crate::rpc::generated_method_kinds::sidecar_method_kind("conversation.list"),
            Some(false)
        );
        assert_eq!(
            crate::rpc::generated_method_kinds::sidecar_method_kind("conversation.create"),
            Some(true)
        );
        // unknown method
        assert!(
            crate::rpc::generated_method_kinds::sidecar_method_kind("nonexistent.method").is_none()
        );
    }
}
