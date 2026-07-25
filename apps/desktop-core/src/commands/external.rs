use crate::error::AppError;
use tracing::info;

#[tauri::command]
pub async fn external_open(url: String) -> Result<(), AppError> {
    info!(url = %url, "command.external_open");
    open::that(&url).map_err(|e| AppError::ExternalOpen(e.to_string()))
}

#[tauri::command]
pub async fn diagnostics_export() -> Result<String, AppError> {
    info!("command.diagnostics_export.start");
    use std::fs;
    use std::path::PathBuf;

    let diag_dir = dirs::data_local_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join("ibreeze")
        .join("diagnostics");

    fs::create_dir_all(&diag_dir).map_err(|e| AppError::Io(e.to_string()))?;

    let timestamp = chrono::Local::now().format("%Y%m%d_%H%M%S");
    let export_path = diag_dir.join(format!("diagnostics_{}.json", timestamp));

    let diagnostics = serde_json::json!({
        "timestamp": chrono::Local::now().to_rfc3339(),
        "platform": std::env::consts::OS,
        "arch": std::env::consts::ARCH,
    });

    fs::write(
        &export_path,
        serde_json::to_string_pretty(&diagnostics).unwrap_or_default(),
    )
    .map_err(|e| AppError::Io(e.to_string()))?;

    let result_path = export_path.to_string_lossy().to_string();
    info!(path = %result_path, "command.diagnostics_export.completed");
    Ok(result_path)
}
