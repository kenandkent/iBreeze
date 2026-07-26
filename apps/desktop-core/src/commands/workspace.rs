use tauri::State;
use tracing::{info, warn};

use crate::commands::AppState;
use crate::error::AppError;
use crate::security::grant_store::GrantKind;

#[tauri::command]
pub async fn workspace_select(
    state: State<'_, AppState>,
    title: Option<String>,
) -> Result<String, AppError> {
    info!(title = ?title, "command.workspace_select.opening");
    let dialog = rfd::FileDialog::new()
        .set_title(title.unwrap_or_else(|| "选择工作区目录".to_string()));

    if let Some(path) = dialog.pick_folder() {
        let grant = state
            .grant_store
            .create_grant(&path, GrantKind::Workspace)
            .await?;
        let grant_id = grant.grant_id.to_string();
        info!(grant_id = %grant_id, "command.workspace_select.selected");
        Ok(grant_id)
    } else {
        warn!("command.workspace_select.cancelled");
        Err(AppError::Cancelled("用户取消选择".to_string()))
    }
}

#[tauri::command]
pub async fn readonly_file_select(
    state: State<'_, AppState>,
    title: Option<String>,
) -> Result<String, AppError> {
    info!(title = ?title, "command.readonly_file_select.opening");
    let dialog = rfd::FileDialog::new()
        .set_title(title.unwrap_or_else(|| "选择文件".to_string()));

    if let Some(path) = dialog.pick_file() {
        let grant = state
            .grant_store
            .create_grant(&path, GrantKind::ReadonlyFile)
            .await?;
        let grant_id = grant.grant_id.to_string();
        info!(grant_id = %grant_id, "command.readonly_file_select.selected");
        Ok(grant_id)
    } else {
        warn!("command.readonly_file_select.cancelled");
        Err(AppError::Cancelled("用户取消选择".to_string()))
    }
}
