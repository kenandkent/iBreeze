use crate::error::AppError;
use tracing::info;

#[tauri::command]
pub async fn external_open(url: String) -> Result<(), AppError> {
    info!(url = %url, "command.external_open");
    open::that(&url).map_err(|e| AppError::ExternalOpen(e.to_string()))
}
