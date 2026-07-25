use crate::error::AppError;
use tracing::{info, warn};

#[tauri::command]
pub async fn workspace_select(title: Option<String>) -> Result<String, AppError> {
    info!(title = ?title, "command.workspace_select.opening");
    let dialog = rfd::FileDialog::new()
        .set_title(title.unwrap_or_else(|| "选择工作区目录".to_string()));

    if let Some(path) = dialog.pick_folder() {
        let path_str = path.to_string_lossy().to_string();
        info!(path = %path_str, "command.workspace_select.selected");
        Ok(path_str)
    } else {
        warn!("command.workspace_select.cancelled");
        Err(AppError::Cancelled("用户取消选择".to_string()))
    }
}

#[tauri::command]
pub async fn readonly_file_select(title: Option<String>) -> Result<String, AppError> {
    info!(title = ?title, "command.readonly_file_select.opening");
    let dialog = rfd::FileDialog::new()
        .set_title(title.unwrap_or_else(|| "选择文件".to_string()));

    if let Some(path) = dialog.pick_file() {
        let path_str = path.to_string_lossy().to_string();
        info!(path = %path_str, "command.readonly_file_select.selected");
        Ok(path_str)
    } else {
        warn!("command.readonly_file_select.cancelled");
        Err(AppError::Cancelled("用户取消选择".to_string()))
    }
}
