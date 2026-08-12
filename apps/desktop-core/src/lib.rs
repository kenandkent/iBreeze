//! iBreeze desktop security and operating-system boundary.

pub mod auth;
pub mod broker;
pub mod commands;
pub mod error;
pub mod ipc;
pub mod keyring;
pub mod process;
pub mod profile;
pub mod rpc;
pub mod security;
pub mod sidecar;
pub mod store;
pub mod trust;
pub mod types;
pub mod update;

use std::path::PathBuf;

use tauri::Manager;
use tracing_subscriber::{fmt, layer::SubscriberExt, util::SubscriberInitExt, EnvFilter};

use crate::commands::{
    diagnostics_export, external_open, readonly_file_select, rpc_request, updater_check,
    updater_install, workspace_select, AppState,
};
use crate::store::LocalStore;

fn init_logging() {
    let log_dir = dirs::data_local_dir()
        .unwrap_or_else(|| std::path::PathBuf::from("."))
        .join("ibreeze")
        .join("logs");
    std::fs::create_dir_all(&log_dir).ok();

    let file_appender = tracing_appender::rolling::Builder::new()
        .rotation(tracing_appender::rolling::Rotation::DAILY)
        .filename_prefix("desktop-core")
        .filename_suffix("log")
        .max_log_files(30)
        .build(log_dir)
        .expect("failed to create log appender");

    let file_layer = fmt::layer()
        .with_writer(file_appender)
        .with_ansi(false)
        .with_target(true)
        .with_thread_ids(true)
        .json();

    let console_layer = fmt::layer()
        .with_target(true)
        .with_writer(std::io::stderr)
        .with_ansi(true);

    let filter = EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info"));

    tracing_subscriber::registry()
        .with(filter)
        .with(console_layer)
        .with(file_layer)
        .init();
}

pub fn run() {
    init_logging();
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
            rpc_request,
            workspace_select,
            readonly_file_select,
            external_open,
            diagnostics_export,
            updater_check,
            updater_install,
        ])
        .run(tauri::generate_context!())
        .expect("error while running iBreeze");
}
