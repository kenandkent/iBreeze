/// Sidecar 客户端，通过 HTTP JSON-RPC 与后端服务通信
use crate::error::AppError;

pub struct SidecarClient {
    base_url: String,
    client: reqwest::Client,
}

impl SidecarClient {
    pub fn new(port: u16) -> Self {
        Self {
            base_url: format!("http://127.0.0.1:{}", port),
            client: reqwest::Client::new(),
        }
    }

    /// 通用 JSON-RPC 调用
    pub async fn call<T: serde::de::DeserializeOwned>(
        &self,
        method: &str,
        params: serde_json::Value,
    ) -> Result<T, AppError> {
        let request = serde_json::json!({
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": 1,
        });

        let response = self
            .client
            .post(&self.base_url)
            .json(&request)
            .send()
            .await
            .map_err(|e| AppError::Network(e.to_string()))?;

        let body: serde_json::Value = response
            .json()
            .await
            .map_err(|e| AppError::Network(e.to_string()))?;

        if let Some(error) = body.get("error") {
            return Err(AppError::Sidecar(
                error
                    .get("message")
                    .and_then(|m| m.as_str())
                    .unwrap_or("Unknown error")
                    .to_string(),
            ));
        }

        let result = body
            .get("result")
            .ok_or_else(|| AppError::Sidecar("No result in response".to_string()))?;

        serde_json::from_value(result.clone()).map_err(|e| AppError::Internal(e.to_string()))
    }

    // === Company 方法 ===

    pub async fn company_create(
        &self,
        data: serde_json::Value,
    ) -> Result<serde_json::Value, AppError> {
        self.call("company.create", data).await
    }

    pub async fn company_list(&self) -> Result<Vec<serde_json::Value>, AppError> {
        self.call("company.list", serde_json::json!({})).await
    }

    pub async fn company_get(&self, id: &str) -> Result<serde_json::Value, AppError> {
        self.call("company.get", serde_json::json!({"id": id}))
            .await
    }

    pub async fn company_update(
        &self,
        id: &str,
        data: serde_json::Value,
    ) -> Result<serde_json::Value, AppError> {
        let mut params = data;
        params["id"] = serde_json::Value::String(id.to_string());
        self.call("company.update", params).await
    }

    pub async fn company_delete(&self, id: &str) -> Result<(), AppError> {
        self.call("company.delete", serde_json::json!({"id": id}))
            .await
    }

    // === Conversation 方法 ===

    pub async fn conversation_create(
        &self,
        title: &str,
    ) -> Result<serde_json::Value, AppError> {
        self.call(
            "conversation.create",
            serde_json::json!({"title": title}),
        )
        .await
    }

    pub async fn conversation_list(&self) -> Result<Vec<serde_json::Value>, AppError> {
        self.call("conversation.list", serde_json::json!({})).await
    }

    pub async fn conversation_get(&self, id: &str) -> Result<serde_json::Value, AppError> {
        self.call("conversation.get", serde_json::json!({"id": id}))
            .await
    }

    pub async fn conversation_archive(&self, id: &str) -> Result<(), AppError> {
        self.call("conversation.archive", serde_json::json!({"id": id}))
            .await
    }

    pub async fn conversation_message_add(
        &self,
        conv_id: &str,
        role: &str,
        content: &str,
    ) -> Result<serde_json::Value, AppError> {
        self.call(
            "conversation.message.add",
            serde_json::json!({
                "conversation_id": conv_id,
                "role": role,
                "content": content,
            }),
        )
        .await
    }

    pub async fn conversation_message_list(
        &self,
        conv_id: &str,
    ) -> Result<Vec<serde_json::Value>, AppError> {
        self.call(
            "conversation.message.list",
            serde_json::json!({"conversation_id": conv_id}),
        )
        .await
    }

    // === Knowledge 方法 ===

    pub async fn knowledge_create(
        &self,
        data: serde_json::Value,
    ) -> Result<serde_json::Value, AppError> {
        self.call("knowledge.create", data).await
    }

    pub async fn knowledge_list(&self) -> Result<Vec<serde_json::Value>, AppError> {
        self.call("knowledge.list", serde_json::json!({})).await
    }

    pub async fn knowledge_search(&self, query: &str) -> Result<Vec<serde_json::Value>, AppError> {
        self.call(
            "knowledge.search",
            serde_json::json!({"query": query}),
        )
        .await
    }

    // === Workspace 方法 ===

    pub async fn workspace_create(
        &self,
        name: &str,
    ) -> Result<serde_json::Value, AppError> {
        self.call("workspace.create", serde_json::json!({"name": name}))
            .await
    }

    pub async fn workspace_list(&self) -> Result<Vec<serde_json::Value>, AppError> {
        self.call("workspace.list", serde_json::json!({})).await
    }

    pub async fn workspace_get(&self, id: &str) -> Result<serde_json::Value, AppError> {
        self.call("workspace.get", serde_json::json!({"id": id}))
            .await
    }

    // === Orchestration 方法 ===

    pub async fn orchestration_create(
        &self,
        name: &str,
    ) -> Result<serde_json::Value, AppError> {
        self.call(
            "orchestration.create",
            serde_json::json!({"name": name}),
        )
        .await
    }

    pub async fn orchestration_list(&self) -> Result<Vec<serde_json::Value>, AppError> {
        self.call("orchestration.list", serde_json::json!({})).await
    }

    pub async fn orchestration_run(&self, id: &str) -> Result<serde_json::Value, AppError> {
        self.call("orchestration.run", serde_json::json!({"id": id}))
            .await
    }

    // === Agent 方法 ===

    pub async fn agent_run(
        &self,
        agent_id: &str,
        message: &str,
    ) -> Result<serde_json::Value, AppError> {
        self.call(
            "agent.run",
            serde_json::json!({"agent_id": agent_id, "message": message}),
        )
        .await
    }

    pub async fn agent_list(&self) -> Result<Vec<serde_json::Value>, AppError> {
        self.call("agent.list", serde_json::json!({})).await
    }

    pub async fn agent_stop(&self, agent_id: &str) -> Result<(), AppError> {
        self.call("agent.stop", serde_json::json!({"agent_id": agent_id}))
            .await
    }

    // === Audit 方法 ===

    pub async fn audit_log(&self, data: serde_json::Value) -> Result<(), AppError> {
        self.call("audit.log", data).await
    }

    pub async fn audit_export(
        &self,
        start_time: &str,
        end_time: &str,
    ) -> Result<Vec<serde_json::Value>, AppError> {
        self.call(
            "audit.export",
            serde_json::json!({"start_time": start_time, "end_time": end_time}),
        )
        .await
    }
}
