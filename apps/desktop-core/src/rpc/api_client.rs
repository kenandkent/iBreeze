/// Backend API HTTP REST 客户端
use crate::error::AppError;

pub struct ApiClient {
    base_url: String,
    client: reqwest::Client,
}

#[derive(Debug, serde::Deserialize)]
pub struct LoginResponse {
    pub access_token: String,
    pub refresh_token: String,
    pub token_type: String,
    pub user_type: String,
    pub pwd_change_required: bool,
}

#[derive(Debug, serde::Deserialize)]
pub struct RegisterResponse {
    pub access_token: String,
    pub token_type: String,
}

#[derive(Debug, serde::Serialize)]
pub struct RegisterRequest {
    pub email: String,
    pub password: String,
    pub confirm_password: String,
}

#[derive(Debug, serde::Serialize)]
pub struct LoginRequest {
    pub email: String,
    pub password: String,
}

#[derive(Debug, serde::Serialize)]
pub struct RefreshRequest {
    pub refresh_token: String,
}

#[derive(Debug, serde::Deserialize)]
pub struct TokenResponse {
    pub access_token: String,
    pub token_type: String,
}

#[derive(Debug, serde::Deserialize)]
pub struct HealthResponse {
    pub status: String,
}

impl ApiClient {
    pub fn new(port: u16) -> Self {
        Self {
            base_url: format!("http://127.0.0.1:{}", port),
            client: reqwest::Client::new(),
        }
    }

    /// 检查后端 API 是否可达
    pub async fn health_check(&self) -> Result<HealthResponse, AppError> {
        let resp = self
            .client
            .get(format!("{}/health", self.base_url))
            .send()
            .await
            .map_err(|e| AppError::Network(format!("Backend API 不可达: {e}")))?;

        resp.json::<HealthResponse>()
            .await
            .map_err(|e| AppError::Network(format!("解析健康检查响应失败: {e}")))
    }

    /// POST /auth/register
    pub async fn register(
        &self,
        email: &str,
        password: &str,
        confirm_password: &str,
    ) -> Result<RegisterResponse, AppError> {
        let body = RegisterRequest {
            email: email.to_string(),
            password: password.to_string(),
            confirm_password: confirm_password.to_string(),
        };

        let resp = self
            .client
            .post(format!("{}/auth/register", self.base_url))
            .json(&body)
            .send()
            .await
            .map_err(|e| AppError::Network(format!("注册请求失败: {e}")))?;

        if !resp.status().is_success() {
            let status = resp.status();
            let text = resp
                .text()
                .await
                .unwrap_or_else(|_| "无法读取错误信息".to_string());
            return Err(AppError::Auth(format!(
                "注册失败 (HTTP {}): {}",
                status, text
            )));
        }

        resp.json::<RegisterResponse>()
            .await
            .map_err(|e| AppError::Network(format!("解析注册响应失败: {e}")))
    }

    /// POST /auth/login
    pub async fn login(&self, email: &str, password: &str) -> Result<LoginResponse, AppError> {
        let body = LoginRequest {
            email: email.to_string(),
            password: password.to_string(),
        };

        let resp = self
            .client
            .post(format!("{}/auth/login", self.base_url))
            .json(&body)
            .send()
            .await
            .map_err(|e| AppError::Network(format!("登录请求失败: {e}")))?;

        if !resp.status().is_success() {
            let status = resp.status();
            let text = resp
                .text()
                .await
                .unwrap_or_else(|_| "无法读取错误信息".to_string());
            return Err(AppError::Auth(format!(
                "登录失败 (HTTP {}): {}",
                status, text
            )));
        }

        resp.json::<LoginResponse>()
            .await
            .map_err(|e| AppError::Network(format!("解析登录响应失败: {e}")))
    }

    /// POST /auth/refresh
    pub async fn refresh_token(&self, refresh_token: &str) -> Result<TokenResponse, AppError> {
        let body = RefreshRequest {
            refresh_token: refresh_token.to_string(),
        };

        let resp = self
            .client
            .post(format!("{}/auth/refresh", self.base_url))
            .json(&body)
            .send()
            .await
            .map_err(|e| AppError::Network(format!("刷新 token 请求失败: {e}")))?;

        if !resp.status().is_success() {
            let status = resp.status();
            let text = resp
                .text()
                .await
                .unwrap_or_else(|_| "无法读取错误信息".to_string());
            return Err(AppError::Auth(format!(
                "刷新 token 失败 (HTTP {}): {}",
                status, text
            )));
        }

        resp.json::<TokenResponse>()
            .await
            .map_err(|e| AppError::Network(format!("解析刷新 token 响应失败: {e}")))
    }

    /// 带 Authorization 的 GET 请求
    pub async fn get(
        &self,
        path: &str,
        token: Option<&str>,
    ) -> Result<serde_json::Value, AppError> {
        let url = format!("{}{}", self.base_url, path);
        let mut req = self.client.get(&url);
        if let Some(t) = token {
            req = req.bearer_auth(t);
        }
        let resp = req
            .send()
            .await
            .map_err(|e| AppError::Network(format!("GET {} 失败: {e}", path)))?;

        if !resp.status().is_success() {
            let status = resp.status();
            let text = resp
                .text()
                .await
                .unwrap_or_else(|_| "无法读取错误信息".to_string());
            return Err(AppError::Network(format!(
                "GET {} 失败 (HTTP {}): {}",
                path, status, text
            )));
        }

        resp.json::<serde_json::Value>()
            .await
            .map_err(|e| AppError::Network(format!("解析 GET {} 响应失败: {e}", path)))
    }

    /// 带 Authorization 的 POST 请求
    pub async fn post(
        &self,
        path: &str,
        body: serde_json::Value,
        token: Option<&str>,
    ) -> Result<serde_json::Value, AppError> {
        let url = format!("{}{}", self.base_url, path);
        let mut req = self.client.post(&url).json(&body);
        if let Some(t) = token {
            req = req.bearer_auth(t);
        }
        let resp = req
            .send()
            .await
            .map_err(|e| AppError::Network(format!("POST {} 失败: {e}", path)))?;

        if !resp.status().is_success() {
            let status = resp.status();
            let text = resp
                .text()
                .await
                .unwrap_or_else(|_| "无法读取错误信息".to_string());
            return Err(AppError::Network(format!(
                "POST {} 失败 (HTTP {}): {}",
                path, status, text
            )));
        }

        resp.json::<serde_json::Value>()
            .await
            .map_err(|e| AppError::Network(format!("解析 POST {} 响应失败: {e}", path)))
    }
}
