//! iBreeze desktop security and operating-system boundary.

pub mod commands;
pub mod error;
pub mod keyring;
pub mod rpc;
pub mod sidecar;
pub mod store;
pub mod trust;
pub mod types;

use std::path::PathBuf;

use tauri::Manager;

use crate::commands::{
    auth_change_password, auth_close_profile, auth_list_offline_profiles, auth_login, auth_logout,
    auth_open_profile, auth_register, backend_validate_origin, rpc_request, AppState,
};
use crate::store::LocalStore;

pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            let app_data = app.path().app_data_dir()?;
            let store = LocalStore::new(app_data);
            let device_id = store
                .initialize()
                .map_err(|error| std::io::Error::other(error.to_string()))?;
            let resource_dir = app.path().resource_dir()?;
            let packaged_sidecar = resource_dir.join("bin").join("ibreeze-sidecar");
            let sidecar_executable = if packaged_sidecar.exists() {
                packaged_sidecar
            } else {
                PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                    .join("..")
                    .join("..")
                    .join("sidecar")
                    .join(".venv")
                    .join("bin")
                    .join("ibreeze-sidecar")
            };
            app.manage(AppState::new(
                store,
                device_id,
                sidecar_executable,
                env!("CARGO_PKG_VERSION").to_owned(),
                cfg!(debug_assertions),
            ));
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            backend_validate_origin,
            auth_register,
            auth_login,
            auth_change_password,
            auth_logout,
            auth_list_offline_profiles,
            auth_open_profile,
            auth_close_profile,
            rpc_request,
        ])
        .run(tauri::generate_context!())
        .expect("error while running iBreeze");
}
