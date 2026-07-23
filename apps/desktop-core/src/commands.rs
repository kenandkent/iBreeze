/// Tauri IPC 命令定义
use tauri::State;

use crate::error::AppError;
use crate::rpc::sidecar::SidecarClient;
use crate::types::*;

/// 应用全局状态
pub struct AppState {
    pub sidecar: SidecarClient,
    pub store: crate::store::Store,
    pub keyring: crate::keyring::Keyring,
    pub auth_token: Option<String>,
    pub current_profile_id: Option<String>,
}

// === Profile 命令 ===

#[tauri::command]
pub async fn get_profile(state: State<'_, AppState>) -> Result<Profile, AppError> {
    let result: serde_json::Value = state
        .sidecar
        .call("profile.get", serde_json::json!({}))
        .await?;
    serde_json::from_value(result).map_err(|e| AppError::Internal(e.to_string()))
}

#[tauri::command]
pub async fn update_profile(
    state: State<'_, AppState>,
    profile: ProfileUpdate,
) -> Result<Profile, AppError> {
    let data = serde_json::to_value(&profile).map_err(|e| AppError::Internal(e.to_string()))?;
    let result: serde_json::Value = state.sidecar.call("profile.update", data).await?;
    serde_json::from_value(result).map_err(|e| AppError::Internal(e.to_string()))
}

#[tauri::command]
pub async fn list_profiles(state: State<'_, AppState>) -> Result<Vec<Profile>, AppError> {
    let result: Vec<serde_json::Value> = state
        .sidecar
        .call("profile.list", serde_json::json!({}))
        .await?;
    result
        .into_iter()
        .map(|v| serde_json::from_value(v).map_err(|e| AppError::Internal(e.to_string())))
        .collect()
}

#[tauri::command]
pub async fn switch_profile(
    state: State<'_, AppState>,
    profile_id: String,
) -> Result<Profile, AppError> {
    let result: serde_json::Value = state
        .sidecar
        .call(
            "profile.switch",
            serde_json::json!({"profile_id": profile_id}),
        )
        .await?;
    serde_json::from_value(result).map_err(|e| AppError::Internal(e.to_string()))
}

// === Auth 命令 ===

#[tauri::command]
pub async fn login(
    state: State<'_, AppState>,
    email: String,
    password: String,
) -> Result<AuthResult, AppError> {
    let result: serde_json::Value = state
        .sidecar
        .call(
            "auth.login",
            serde_json::json!({"email": email, "password": password}),
        )
        .await?;
    serde_json::from_value(result).map_err(|e| AppError::Internal(e.to_string()))
}

#[tauri::command]
pub async fn logout(state: State<'_, AppState>) -> Result<(), AppError> {
    state
        .sidecar
        .call("auth.logout", serde_json::json!({}))
        .await
}

#[tauri::command]
pub async fn refresh_token(state: State<'_, AppState>) -> Result<AuthResult, AppError> {
    let result: serde_json::Value = state
        .sidecar
        .call("auth.refresh", serde_json::json!({}))
        .await?;
    serde_json::from_value(result).map_err(|e| AppError::Internal(e.to_string()))
}

// === Company 命令 ===

#[tauri::command]
pub async fn create_company(
    state: State<'_, AppState>,
    data: CompanyCreate,
) -> Result<Company, AppError> {
    let params = serde_json::to_value(&data).map_err(|e| AppError::Internal(e.to_string()))?;
    let result: serde_json::Value = state.sidecar.company_create(params).await?;
    serde_json::from_value(result).map_err(|e| AppError::Internal(e.to_string()))
}

#[tauri::command]
pub async fn list_companies(state: State<'_, AppState>) -> Result<Vec<Company>, AppError> {
    let result: Vec<serde_json::Value> = state.sidecar.company_list().await?;
    result
        .into_iter()
        .map(|v| serde_json::from_value(v).map_err(|e| AppError::Internal(e.to_string())))
        .collect()
}

#[tauri::command]
pub async fn get_company(state: State<'_, AppState>, id: String) -> Result<Company, AppError> {
    let result: serde_json::Value = state.sidecar.company_get(&id).await?;
    serde_json::from_value(result).map_err(|e| AppError::Internal(e.to_string()))
}

#[tauri::command]
pub async fn update_company(
    state: State<'_, AppState>,
    id: String,
    data: CompanyUpdate,
) -> Result<Company, AppError> {
    let params = serde_json::to_value(&data).map_err(|e| AppError::Internal(e.to_string()))?;
    let result: serde_json::Value = state.sidecar.company_update(&id, params).await?;
    serde_json::from_value(result).map_err(|e| AppError::Internal(e.to_string()))
}

#[tauri::command]
pub async fn delete_company(state: State<'_, AppState>, id: String) -> Result<(), AppError> {
    state.sidecar.company_delete(&id).await
}

// === Conversation 命令 ===

#[tauri::command]
pub async fn create_conversation(
    state: State<'_, AppState>,
    title: String,
) -> Result<Conversation, AppError> {
    let result: serde_json::Value = state.sidecar.conversation_create(&title).await?;
    serde_json::from_value(result).map_err(|e| AppError::Internal(e.to_string()))
}

#[tauri::command]
pub async fn list_conversations(
    state: State<'_, AppState>,
) -> Result<Vec<Conversation>, AppError> {
    let result: Vec<serde_json::Value> = state.sidecar.conversation_list().await?;
    result
        .into_iter()
        .map(|v| serde_json::from_value(v).map_err(|e| AppError::Internal(e.to_string())))
        .collect()
}

#[tauri::command]
pub async fn get_conversation(
    state: State<'_, AppState>,
    id: String,
) -> Result<Conversation, AppError> {
    let result: serde_json::Value = state.sidecar.conversation_get(&id).await?;
    serde_json::from_value(result).map_err(|e| AppError::Internal(e.to_string()))
}

#[tauri::command]
pub async fn archive_conversation(
    state: State<'_, AppState>,
    id: String,
) -> Result<(), AppError> {
    state.sidecar.conversation_archive(&id).await
}

#[tauri::command]
pub async fn add_message(
    state: State<'_, AppState>,
    conversation_id: String,
    content: String,
    role: String,
) -> Result<Message, AppError> {
    let result: serde_json::Value = state
        .sidecar
        .conversation_message_add(&conversation_id, &role, &content)
        .await?;
    serde_json::from_value(result).map_err(|e| AppError::Internal(e.to_string()))
}

#[tauri::command]
pub async fn list_messages(
    state: State<'_, AppState>,
    conversation_id: String,
) -> Result<Vec<Message>, AppError> {
    let result: Vec<serde_json::Value> = state
        .sidecar
        .conversation_message_list(&conversation_id)
        .await?;
    result
        .into_iter()
        .map(|v| serde_json::from_value(v).map_err(|e| AppError::Internal(e.to_string())))
        .collect()
}

// === Knowledge 命令 ===

#[tauri::command]
pub async fn create_knowledge_entry(
    state: State<'_, AppState>,
    data: KnowledgeEntryCreate,
) -> Result<KnowledgeEntry, AppError> {
    let params = serde_json::to_value(&data).map_err(|e| AppError::Internal(e.to_string()))?;
    let result: serde_json::Value = state.sidecar.knowledge_create(params).await?;
    serde_json::from_value(result).map_err(|e| AppError::Internal(e.to_string()))
}

#[tauri::command]
pub async fn list_knowledge_entries(
    state: State<'_, AppState>,
) -> Result<Vec<KnowledgeEntry>, AppError> {
    let result: Vec<serde_json::Value> = state.sidecar.knowledge_list().await?;
    result
        .into_iter()
        .map(|v| serde_json::from_value(v).map_err(|e| AppError::Internal(e.to_string())))
        .collect()
}

#[tauri::command]
pub async fn search_knowledge(
    state: State<'_, AppState>,
    query: String,
) -> Result<Vec<KnowledgeEntry>, AppError> {
    let result: Vec<serde_json::Value> = state.sidecar.knowledge_search(&query).await?;
    result
        .into_iter()
        .map(|v| serde_json::from_value(v).map_err(|e| AppError::Internal(e.to_string())))
        .collect()
}

// === Workspace 命令 ===

#[tauri::command]
pub async fn create_workspace(
    state: State<'_, AppState>,
    name: String,
) -> Result<Workspace, AppError> {
    let result: serde_json::Value = state.sidecar.workspace_create(&name).await?;
    serde_json::from_value(result).map_err(|e| AppError::Internal(e.to_string()))
}

#[tauri::command]
pub async fn list_workspaces(state: State<'_, AppState>) -> Result<Vec<Workspace>, AppError> {
    let result: Vec<serde_json::Value> = state.sidecar.workspace_list().await?;
    result
        .into_iter()
        .map(|v| serde_json::from_value(v).map_err(|e| AppError::Internal(e.to_string())))
        .collect()
}

#[tauri::command]
pub async fn get_workspace(
    state: State<'_, AppState>,
    id: String,
) -> Result<Workspace, AppError> {
    let result: serde_json::Value = state.sidecar.workspace_get(&id).await?;
    serde_json::from_value(result).map_err(|e| AppError::Internal(e.to_string()))
}

// === Orchestration 命令 ===

#[tauri::command]
pub async fn create_orchestration(
    state: State<'_, AppState>,
    name: String,
) -> Result<Orchestration, AppError> {
    let result: serde_json::Value = state.sidecar.orchestration_create(&name).await?;
    serde_json::from_value(result).map_err(|e| AppError::Internal(e.to_string()))
}

#[tauri::command]
pub async fn list_orchestrations(
    state: State<'_, AppState>,
) -> Result<Vec<Orchestration>, AppError> {
    let result: Vec<serde_json::Value> = state.sidecar.orchestration_list().await?;
    result
        .into_iter()
        .map(|v| serde_json::from_value(v).map_err(|e| AppError::Internal(e.to_string())))
        .collect()
}

#[tauri::command]
pub async fn run_orchestration(
    state: State<'_, AppState>,
    id: String,
) -> Result<OrchestrationRun, AppError> {
    let result: serde_json::Value = state.sidecar.orchestration_run(&id).await?;
    serde_json::from_value(result).map_err(|e| AppError::Internal(e.to_string()))
}

// === Agent 命令 ===

#[tauri::command]
pub async fn run_agent(
    state: State<'_, AppState>,
    agent_id: String,
    message: String,
) -> Result<AgentResponse, AppError> {
    let result: serde_json::Value = state.sidecar.agent_run(&agent_id, &message).await?;
    serde_json::from_value(result).map_err(|e| AppError::Internal(e.to_string()))
}

#[tauri::command]
pub async fn list_agents(state: State<'_, AppState>) -> Result<Vec<AgentInfo>, AppError> {
    let result: Vec<serde_json::Value> = state.sidecar.agent_list().await?;
    result
        .into_iter()
        .map(|v| serde_json::from_value(v).map_err(|e| AppError::Internal(e.to_string())))
        .collect()
}

#[tauri::command]
pub async fn stop_agent(state: State<'_, AppState>, agent_id: String) -> Result<(), AppError> {
    state.sidecar.agent_stop(&agent_id).await
}

// === Security 命令 ===

#[tauri::command]
pub async fn generate_keypair(state: State<'_, AppState>) -> Result<KeyPairInfo, AppError> {
    let result: serde_json::Value = state
        .sidecar
        .call("security.keypair.generate", serde_json::json!({}))
        .await?;
    serde_json::from_value(result).map_err(|e| AppError::Internal(e.to_string()))
}

#[tauri::command]
pub async fn sign_data(
    state: State<'_, AppState>,
    data: String,
    key_id: String,
) -> Result<String, AppError> {
    let result: serde_json::Value = state
        .sidecar
        .call(
            "security.sign",
            serde_json::json!({"data": data, "key_id": key_id}),
        )
        .await?;
    result
        .as_str()
        .map(|s| s.to_string())
        .ok_or_else(|| AppError::Internal("Invalid signature response".to_string()))
}

#[tauri::command]
pub async fn verify_signature(
    state: State<'_, AppState>,
    data: String,
    signature: String,
    key_id: String,
) -> Result<bool, AppError> {
    let result: serde_json::Value = state
        .sidecar
        .call(
            "security.verify",
            serde_json::json!({"data": data, "signature": signature, "key_id": key_id}),
        )
        .await?;
    result
        .as_bool()
        .ok_or_else(|| AppError::Internal("Invalid verify response".to_string()))
}

// === Release 命令 ===

#[tauri::command]
pub async fn check_update(
    state: State<'_, AppState>,
) -> Result<Option<UpdateInfo>, AppError> {
    let result: serde_json::Value = state
        .sidecar
        .call("release.check", serde_json::json!({}))
        .await?;
    if result.is_null() {
        return Ok(None);
    }
    serde_json::from_value(result)
        .map(Some)
        .map_err(|e| AppError::Internal(e.to_string()))
}

#[tauri::command]
pub async fn apply_update(
    state: State<'_, AppState>,
    update_info: UpdateInfo,
) -> Result<(), AppError> {
    let params =
        serde_json::to_value(&update_info).map_err(|e| AppError::Internal(e.to_string()))?;
    state
        .sidecar
        .call("release.apply", params)
        .await
}
