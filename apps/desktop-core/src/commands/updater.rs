use tracing::{error, info, warn};
use uuid::Uuid;

use crate::error::AppError;
use crate::types::{UpdaterCheckResult, UpdaterInstallResult};
use crate::update::manifest::{is_newer_version, validate_manifest, UpdateManifest};
use crate::update::rollback::UpdateStore;

use crate::commands::AppState;
use crate::trust::verify_catalog_keyset;
use tauri::State;

#[tauri::command]
pub async fn updater_check(state: State<'_, AppState>) -> Result<UpdaterCheckResult, AppError> {
    info!("command.updater_check.start");

    let current_version = state.app_version.clone();

    let manifest_url = format!(
        "https://releases.ibreeze.ai/{}/update.json",
        current_version
    );

    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(15))
        .build()
        .map_err(|e| AppError::Network(e.to_string()))?;

    let response = client.get(&manifest_url).send().await;
    let manifest: UpdateManifest = match response {
        Ok(resp) if resp.status().is_success() => resp.json().await.map_err(|e| {
            error!("UPDATE_MANIFEST_PARSE_FAILED: {e}");
            AppError::Network("UPDATE_MANIFEST_PARSE_FAILED".to_owned())
        })?,
        Ok(resp) if resp.status() == reqwest::StatusCode::NOT_FOUND => {
            info!("UPDATE_NO_UPDATE_AVAILABLE");
            return Ok(UpdaterCheckResult {
                available: false,
                current_version: current_version.clone(),
                latest_version: current_version.clone(),
                published_at: None,
                package_url: None,
                package_sha256: None,
            });
        }
        Ok(resp) => {
            warn!(status = %resp.status(), "UPDATE_CHECK_FAILED");
            return Ok(UpdaterCheckResult {
                available: false,
                current_version: current_version.clone(),
                latest_version: current_version.clone(),
                published_at: None,
                package_url: None,
                package_sha256: None,
            });
        }
        Err(e) => {
            warn!(error = %e, "UPDATE_NETWORK_ERROR");
            return Err(AppError::Network(format!("UPDATE_NETWORK_ERROR: {e}")));
        }
    };

    let update_available = is_newer_version(&manifest.version, &current_version);

    if update_available {
        info!(
            current = %current_version,
            latest = %manifest.version,
            "UPDATE_AVAILABLE"
        );
        Ok(UpdaterCheckResult {
            available: true,
            current_version: current_version.clone(),
            latest_version: manifest.version.clone(),
            published_at: Some(manifest.published_at.to_rfc3339()),
            package_url: Some(manifest.package_url.clone()),
            package_sha256: Some(manifest.package_sha256.clone()),
        })
    } else {
        info!("UPDATE_ALREADY_LATEST");
        Ok(UpdaterCheckResult {
            available: false,
            current_version: current_version.clone(),
            latest_version: current_version,
            published_at: None,
            package_url: None,
            package_sha256: None,
        })
    }
}

#[tauri::command]
pub async fn updater_install(state: State<'_, AppState>) -> Result<UpdaterInstallResult, AppError> {
    info!("command.updater_install.start");

    let current_version = state.app_version.clone();
    let base_path = state.store.base_path().to_path_buf();
    let update_store = UpdateStore::new(base_path.clone());

    let manifest_url = format!(
        "https://releases.ibreeze.ai/{}/update.json",
        current_version
    );

    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(120))
        .build()
        .map_err(|e| AppError::Network(e.to_string()))?;

    let manifest: UpdateManifest = client
        .get(&manifest_url)
        .send()
        .await
        .map_err(|e| AppError::Network(format!("UPDATE_FETCH_MANIFEST_FAILED: {e}")))?
        .json()
        .await
        .map_err(|e| {
            error!("UPDATE_MANIFEST_PARSE_FAILED: {e}");
            AppError::Network("UPDATE_MANIFEST_PARSE_FAILED".to_owned())
        })?;

    let package_path = base_path
        .join("update")
        .join("staging")
        .join(format!("package-{}.tar.gz", Uuid::new_v4()));

    std::fs::create_dir_all(package_path.parent().unwrap())
        .map_err(|e| AppError::Storage(format!("create staging dir: {e}")))?;

    let download_result = client.get(&manifest.package_url).send().await;

    match download_result {
        Ok(resp) if resp.status().is_success() => {
            let bytes = resp.bytes().await.map_err(|e| {
                error!("UPDATE_DOWNLOAD_FAILED: {e}");
                AppError::Network("UPDATE_DOWNLOAD_FAILED".to_owned())
            })?;

            std::fs::write(&package_path, &bytes)
                .map_err(|e| AppError::Storage(format!("write package: {e}")))?;

            let package_bytes = std::fs::read(&package_path)
                .map_err(|e| AppError::Storage(format!("read package: {e}")))?;

            let trusted_keys = load_trusted_signing_keys(&state).await?;

            match validate_manifest(&manifest, &current_version, &trusted_keys, &package_bytes) {
                Ok(()) => {
                    let install_path = &base_path;
                    let (backup_id, backup_sha) =
                        update_store.cache_current_install(install_path, &current_version)?;

                    update_store.create_pending_marker(
                        &current_version,
                        &manifest.version,
                        &backup_id,
                        &backup_sha,
                    )?;

                    UpdateStore::safe_extract(&package_path, install_path)?;

                    update_store.cleanup_staging(&package_path);
                    info!(
                        version = %manifest.version,
                        "UPDATE_INSTALLED"
                    );

                    Ok(UpdaterInstallResult {
                        success: true,
                        new_version: manifest.version.clone(),
                    })
                }
                Err(e) => {
                    update_store.cleanup_staging(&package_path);
                    error!(error = %e, "UPDATE_VALIDATION_FAILED");
                    Err(e)
                }
            }
        }
        Ok(resp) => {
            update_store.cleanup_staging(&package_path);
            error!(status = %resp.status(), "UPDATE_DOWNLOAD_FAILED");
            Err(AppError::Network(format!(
                "UPDATE_DOWNLOAD_FAILED: HTTP {}",
                resp.status()
            )))
        }
        Err(e) => {
            update_store.cleanup_staging(&package_path);
            error!(error = %e, "UPDATE_NETWORK_DOWNLOAD_FAILED");
            Err(AppError::Network(format!(
                "UPDATE_NETWORK_DOWNLOAD_FAILED: {e}"
            )))
        }
    }
}

#[tauri::command]
pub async fn updater_verify_launch(state: State<'_, AppState>) -> Result<bool, AppError> {
    let update_store = UpdateStore::new(state.store.base_path().to_path_buf());
    let result =
        update_store.verify_pending_update(&state.sidecar_executable, &state.app_version)?;
    Ok(result)
}

async fn load_trusted_signing_keys(
    state: &State<'_, AppState>,
) -> Result<Vec<crate::rpc::api_client::SigningKey>, AppError> {
    let profile_directory_id = state
        .auth
        .read()
        .await
        .profile_directory_id
        .clone()
        .ok_or_else(|| AppError::NotFound("UPDATE_NO_OPEN_PROFILE".to_owned()))?;
    let keyset = super::load_catalog_keyset(state, &profile_directory_id)?;
    verify_catalog_keyset(&keyset, state.development_mode, false)
}

#[tauri::command]
pub async fn updater_restore_stable(state: State<'_, AppState>) -> Result<bool, AppError> {
    info!("command.updater_restore_stable.start");
    let update_store = UpdateStore::new(state.store.base_path().to_path_buf());
    let marker = update_store
        .load_pending_marker()?
        .ok_or_else(|| AppError::NotFound("UPDATE_NO_PENDING_MARKER".to_owned()))?;

    let install_path = state.store.base_path().to_path_buf();
    update_store.restore_backup(&install_path, &marker.backup_id)?;
    update_store.delete_pending_marker()?;
    info!(version = %marker.old_version, "UPDATE_RESTORED_STABLE");
    Ok(true)
}
