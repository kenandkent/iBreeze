# 管理后台 API 文档

## 概述

iBreeze 后端 API 提供 RESTful 接口，用于管理用户、技能、目录和审计日志。

## 基础信息

- **Base URL**: `http://localhost:51080/api/v1`
- **认证方式**: Bearer Token
- **Content-Type**: `application/json`

## 认证

### 获取 Token

```http
POST /auth/login
Content-Type: application/json

{
  "username": "admin",
  "password": "your-password"
}
```

响应：
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer"
}
```

### 使用 Token

```http
GET /users
Authorization: Bearer eyJ...
```

## 用户管理

### 创建用户

```http
POST /users
Content-Type: application/json
Authorization: Bearer <token>

{
  "username": "newuser",
  "email": "user@example.com",
  "password": "securepassword",
  "role": "editor"
}
```

响应：
```json
{
  "id": "uuid",
  "username": "newuser",
  "email": "user@example.com",
  "role": "editor",
  "is_active": true
}
```

### 获取用户列表

```http
GET /users?skip=0&limit=100
Authorization: Bearer <token>
```

响应：
```json
{
  "users": [...],
  "total": 50
}
```

### 获取单个用户

```http
GET /users/{user_id}
Authorization: Bearer <token>
```

### 更新用户

```http
PUT /users/{user_id}
Content-Type: application/json
Authorization: Bearer <token>

{
  "email": "newemail@example.com",
  "role": "admin",
  "is_active": true
}
```

### 删除用户

```http
DELETE /users/{user_id}
Authorization: Bearer <token>
```

## 技能管理

### 获取技能列表

```http
GET /skills?category=productivity&skip=0&limit=100
Authorization: Bearer <token>
```

### 获取单个技能

```http
GET /skills/{skill_id}
Authorization: Bearer <token>
```

### 创建技能

```http
POST /skills
Content-Type: application/json
Authorization: Bearer <token>

{
  "name": "Code Reviewer",
  "version": "1.0.0",
  "category": "development",
  "description": "Automated code review skill",
  "compatibility": {
    "min_platform": "1.0.0"
  }
}
```

### 更新技能

```http
PUT /skills/{skill_id}
Content-Type: application/json
Authorization: Bearer <token>

{
  "description": "Updated description",
  "is_active": false
}
```

### 上传技能包

```http
POST /skills/upload
Content-Type: multipart/form-data
Authorization: Bearer <token>

file: <skill.zip>
```

## 目录管理

### 获取发布列表

```http
GET /catalog/releases
Authorization: Bearer <token>
```

### 创建发布

```http
POST /catalog/releases
Content-Type: application/json
Authorization: Bearer <token>

{
  "version": "2024.01.15",
  "notes": "Weekly release update"
}
```

### 发布目录

```http
POST /catalog/releases/{release_id}/publish
Authorization: Bearer <token>
```

### 模型管理

```http
GET /admin/api/v1/models
Authorization: Bearer <token>
```

响应：
```json
{
  "data": [
    {
      "id": "uuid",
      "provider_key": "openai",
      "model_key": "gpt-4",
      "display_name": "GPT-4",
      "context_window": 8192,
      "supports_tools": true,
      "supports_streaming": true,
      "supports_vision": false,
      "status": "published"
    }
  ]
}
```

```http
POST /admin/api/v1/models
Authorization: Bearer <token>
Content-Type: application/json

{
  "provider_key": "openai",
  "model_key": "gpt-4",
  "display_name": "GPT-4",
  "context_window": 8192,
  "supports_tools": true,
  "supports_streaming": true,
  "supports_vision": false
}
```

```http
PATCH /admin/api/v1/models/{model_id}
Authorization: Bearer <token>
If-Match: "<version>"
```

```http
DELETE /admin/api/v1/models/{model_id}
Authorization: Bearer <token>
If-Match: "<version>"
```

### Provider 管理

```http
GET /admin/api/v1/providers
Authorization: Bearer <token>
```

```http
POST /admin/api/v1/providers
Authorization: Bearer <token>
Content-Type: application/json

{
  "key": "openai",
  "display_name": "OpenAI",
  "protocol": "openai",
  "base_url": "https://api.openai.com/v1",
  "status": "draft"
}
```

```http
PATCH /admin/api/v1/providers/{provider_id}
Authorization: Bearer <token>
If-Match: "<version>"
```

### Agent-Model 绑定

```http
GET /admin/api/v1/agent-model-bindings
Authorization: Bearer <token>
```

```http
POST /admin/api/v1/agent-model-bindings
Authorization: Bearer <token>
Content-Type: application/json

{
  "agent_id": "uuid",
  "model_id": "uuid",
  "min_version": "1.0.0",
  "max_version": "2.0.0"
}
```

### Provider-Model 绑定

```http
GET /admin/api/v1/provider-model-bindings
Authorization: Bearer <token>
```

```http
POST /admin/api/v1/provider-model-bindings
Authorization: Bearer <token>
Content-Type: application/json

{
  "provider_id": "uuid",
  "model_id": "uuid",
  "protocol": "openai"
}
```

### 目录验证

```http
POST /admin/api/v1/catalog/validate
Authorization: Bearer <token>
```

响应：
```json
{
  "data": {
    "passed": true,
    "issues": []
  }
}
```

### 获取 Manifest

```http
GET /catalog/manifest
Authorization: Bearer <token>
```

响应：
```json
{
  "version": "2024.01.15",
  "generated_at": "2024-01-15T10:00:00Z",
  "skills": [
    {
      "id": "uuid",
      "name": "Code Reviewer",
      "version": "1.0.0",
      "category": "development"
    }
  ]
}
```

## 审计日志

### 获取审计日志

```http
GET /audit?user_id=uuid&action=create&resource_type=user&skip=0&limit=100
Authorization: Bearer <token>
```

响应：
```json
{
  "logs": [
    {
      "id": "uuid",
      "user_id": "uuid",
      "action": "create",
      "resource_type": "user",
      "resource_id": "uuid",
      "details": {...},
      "ip_address": "127.0.0.1",
      "created_at": "2024-01-15T10:00:00Z"
    }
  ],
  "total": 100
}
```

## 公开目录查询

### 获取 Agent 目录

```http
GET /api/v1/catalog/agents
```

响应：
```json
{
  "agents": [
    {
      "id": "uuid",
      "key": "agent-key",
      "display_name": "Agent Name",
      "status": "published"
    }
  ]
}
```

### 获取 Agent 模型

```http
GET /api/v1/catalog/agents/{agent_id}/models
```

响应：
```json
{
  "models": [
    {
      "id": "uuid",
      "model_key": "model-key",
      "display_name": "Model Name"
    }
  ]
}
```

### 获取 Provider 目录

```http
GET /api/v1/catalog/providers
```

响应：
```json
{
  "providers": [
    {
      "id": "uuid",
      "display_name": "OpenAI",
      "status": "published"
    }
  ]
}
```

### 获取 Provider 模型

```http
GET /api/v1/catalog/providers/{provider_id}/models
```

响应：
```json
{
  "models": [
    {
      "id": "uuid",
      "model_key": "gpt-4",
      "display_name": "GPT-4"
    }
  ]
}
```

### 获取技能目录

```http
GET /api/v1/catalog/skills
```

响应：
```json
{
  "skills": [
    {
      "id": "uuid",
      "key": "skill-key",
      "display_name": "Skill Name",
      "status": "published"
    }
  ]
}
```

### 获取最新紧急禁用规则

```http
GET /api/v1/catalog/emergency-disables/latest
```

响应：
```json
{
  "rules": [
    {
      "id": "uuid",
      "subject_type": "agent",
      "subject_id": "agent-id",
      "reason": "Security vulnerability"
    }
  ]
}
```

## 健康检查

### 基础健康检查

```http
GET /health
```

响应：
```json
{
  "status": "ok"
}
```

### 就绪检查

```http
GET /health/ready
```

响应：
```json
{
  "status": "ready",
  "database": "connected"
}
```

## 错误处理

### 错误响应格式

所有错误遵循 RFC 9457 Problem Details 格式：

```json
{
  "type": "about:blank",
  "title": "错误标题",
  "status": 400,
  "code": "ERROR_CODE",
  "detail": "错误详情描述",
  "request_id": "请求跟踪ID",
  "field_errors": {
    "field_name": ["错误1", "错误2"]
  }
}
```

字段说明：
- `type`: 错误类型 URI（当前固定为 `about:blank`）
- `title`: 错误标题
- `status`: HTTP 状态码
- `code`: 稳定错误码（用于客户端逻辑判断）
- `detail`: 错误详情
- `request_id`: 请求跟踪 ID（用于问题排查）
- `field_errors`: 字段级别的错误（仅 422 响应中包含）

### 常见错误码

| 状态码 | 错误码 | 说明 |
|--------|--------|------|
| 400 | IF_MATCH_INVALID | If-Match 头无效 |
| 401 | AUTH_INVALID_CREDENTIALS | 认证凭证无效 |
| 401 | AUTH_TOKEN_EXPIRED | Token 已过期 |
| 401 | AUTH_TOKEN_INVALID | Token 无效 |
| 401 | AUTH_MISSING_TOKEN | 缺少认证 Token |
| 401 | AUTH_TOKEN_REPLAY | Token 重放攻击 |
| 401 | AUTH_SESSION_REVOKED | Session 已被撤销 |
| 401 | AUTH_USER_DISABLED | 用户已被禁用 |
| 403 | AUTH_PASSWORD_CHANGE_REQUIRED | 需要修改密码 |
| 403 | PROTECTED_USER_OPERATION_DENIED | 受保护用户操作被拒绝 |
| 404 | USER_NOT_FOUND | 用户不存在 |
| 404 | CATALOG_RESOURCE_NOT_FOUND | 目录资源不存在 |
| 404 | RELEASE_NOT_FOUND | 发布记录不存在 |
| 404 | SKILL_PACKAGE_NOT_FOUND | Skill 包不存在 |
| 404 | EMERGENCY_DISABLE_NOT_FOUND | 紧急禁用记录不存在 |
| 409 | AUTH_EMAIL_EXISTS | 邮箱已注册 |
| 409 | CATALOG_LOGICAL_KEY_EXISTS | 逻辑键已存在 |
| 409 | CATALOG_REVISION_IMMUTABLE | 修订版本不可变 |
| 409 | OPTIMISTIC_LOCK_CONFLICT | 乐观锁冲突 |
| 422 | SKILL_PACKAGE_EXTENSION_INVALID | Skill 包扩展名无效 |
| 428 | IF_MATCH_REQUIRED | 需要 If-Match 头 |

## 限流

- 默认限制：100 请求/分钟
- 通过 `X-RateLimit-*` 响应头查看限制信息

## 版本控制

API 版本通过 URL 路径控制：`/api/v1/...`

未来版本将添加：`/api/v2/...`
