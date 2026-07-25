use crate::error::AppError;
use tracing::{info, warn};

#[tauri::command]
pub async fn updater_check() -> Result<serde_json::Value, AppError> {
    info!("command.updater_check.start");
    let result = serde_json::json!({
        "available": false,
        "current_version": env!("CARGO_PKG_VERSION"),
        "latest_version": env!("CARGO_PKG_VERSION"),
    });
    info!(available = false, "command.updater_check.completed");
    Ok(result)
}

#[tauri::command]
pub async fn updater_install() -> Result<(), AppError> {
    warn!("command.updater_install.not_supported");
    Err(AppError::NotSupported("自动更新暂未实现".to_string()))
}
