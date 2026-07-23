# 管理后台 API 文档

## 概述

iBreeze 后端 API 提供 RESTful 接口，用于管理用户、技能、目录和审计日志。

## 基础信息

- **Base URL**: `http://localhost:8000/api/v1`
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

```json
{
  "detail": "Error message"
}
```

### 常见错误码

| 状态码 | 说明 |
|--------|------|
| 400 | 请求参数错误 |
| 401 | 未认证 |
| 403 | 无权限 |
| 404 | 资源不存在 |
| 422 | 请求体验证失败 |
| 500 | 服务器内部错误 |

## 限流

- 默认限制：100 请求/分钟
- 通过 `X-RateLimit-*` 响应头查看限制信息

## 版本控制

API 版本通过 URL 路径控制：`/api/v1/...`

未来版本将添加：`/api/v2/...`
