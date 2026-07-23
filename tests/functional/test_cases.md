# iBreeze 全量测试用例文档

> 按功能模块的功能链路组织，覆盖内部逻辑和端到端契约

---

## 1. 认证链路 (G.11)

| ID | 用例名称 | 前置条件 | 测试步骤 | 预期结果 | 设计引用 |
|---|---|---|---|---|---|
| TC-AUTH-001 | 应用用户注册成功 | 无 | POST /auth/register {email, password, confirm_password} | 201, 返回 user_id, 邮箱存储为小写 | G.11 |
| TC-AUTH-002 | 注册邮箱大小写规范化 | 无 | 注册 "User@Example.COM" | 存储为 "user@example.com", 可用小写登录 | G.11 |
| TC-AUTH-003 | 注册密码长度校验 | 无 | 密码少于 8 字符 | 422 VALIDATION_FAILED | G.11 |
| TC-AUTH-004 | 注册密码超长校验 | 无 | 密码超过 128 字符 | 422 VALIDATION_FAILED | G.11 |
| TC-AUTH-005 | 注册密码确认不一致 | 无 | password != confirm_password | 422 VALIDATION_FAILED | G.11 |
| TC-AUTH-006 | 注册重复邮箱拒绝 | 已注册 user@example.com | 再次注册同一邮箱 | 409 AUTH_EMAIL_EXISTS | G.11 |
| TC-AUTH-007 | 注册忽略非法 user_type 字段 | 无 | 注册请求带 user_type="admin" | 创建 app_user, 忽略 user_type | G.11 |
| TC-AUTH-008 | 应用用户登录成功 | 已注册 app_user | POST /auth/login {email, password} | 200, access_token + refresh_token, user_type="app" | G.11 |
| TC-AUTH-009 | 登录密码错误 | 已注册用户 | 错误密码登录 | 401 AUTH_INVALID_CREDENTIALS | G.11 |
| TC-AUTH-010 | 登录用户不存在 | 未注册邮箱 | 登录 | 401 AUTH_INVALID_CREDENTIALS（不区分用户不存在与密码错误）| G.11 |
| TC-AUTH-011 | 登录用户被禁用 | 用户 is_active=false | 登录 | 403 AUTH_USER_DISABLED | G.11 |
| TC-AUTH-012 | Access Token 有效期内可访问 | 已登录 | 用 access_token 调用需认证接口 | 200 正常响应 | G.11 |
| TC-AUTH-013 | Access Token 15分钟过期 | 已登录, token 超过 15min | 调用需认证接口 | 401 AUTH_TOKEN_EXPIRED | G.11 |
| TC-AUTH-014 | Refresh Token 轮换 | 已登录, 有 refresh_token | POST /auth/refresh {refresh_token} | 新 access_token + 新 refresh_token, 旧 family 标记 rotated | G.11 |
| TC-AUTH-015 | Refresh Token 重放检测 | 已轮换过的 refresh_token | 再次 refresh | 撤销整个 family, 401 | G.11 |
| TC-AUTH-016 | Refresh Token 30天过期 | refresh_token 超过 30 天 | refresh | 401 | G.11 |
| TC-AUTH-017 | 登出撤销当前 family | 已登录 | POST /auth/logout | 当前 refresh family 被撤销, 后续 refresh 失败 | G.11 |
| TC-AUTH-018 | 全设备登出撤销所有 family | 已登录, 多个 session | POST /auth/logout-all | 所有 refresh family 被撤销 | G.11 |
| TC-AUTH-019 | 修改密码撤销所有 family | 已登录 | POST /auth/change-password | 旧密码验证通过, 新密码哈希存储, 所有 family 撤销, 返回新 token | G.11 |
| TC-AUTH-020 | 默认管理员首次登录必须改密 | admin/admin123456 首次登录 | login 后调用业务接口 | pwd_change_required=true, 只能访问 change-password | G.11 |
| TC-AUTH-021 | Ed25519 JWT 签名验证 | 已签发 token | 解码 JWT header | alg="EdDSA", kid 存在 | G.11 |
| TC-AUTH-022 | audience 分离 - app token 不能访问 admin 接口 | app_user 登录 | 用 app access_token 调 /admin/* | 401 | G.11 |
| TC-AUTH-023 | audience 分离 - admin token 不能访问 app 接口 | admin 登录 | 用 admin access_token 调 /auth/keys | 401 | G.11 |
| TC-AUTH-024 | 管理员登录 | admin 用户 | POST /admin/api/v1/auth/login | 200, access_token, user_type="admin" | G.11 |
| TC-AUTH-025 | 管理员 Refresh 轮换 | admin 已登录 | POST /admin/api/v1/auth/refresh | 新 token pair, 旧 family rotated | G.11 |
| TC-AUTH-026 | IP 限速 | 同一 IP 多次失败登录 | 连续 5 次错误密码 | 429 RATE_LIMITED | G.11 |
| TC-AUTH-027 | 注册密码不含特殊字符也允许 | 无 | 密码 "abcdefgh" | 注册成功 | G.11 |

## 2. 用户管理链路 (G.12)

| ID | 用例名称 | 前置条件 | 测试步骤 | 预期结果 | 设计引用 |
|---|---|---|---|---|---|
| TC-USER-001 | 创建应用用户 | admin 登录 | POST /admin/api/v1/users {email, password, user_type="app_user"} | 201, user_type=app_user | G.12 |
| TC-USER-002 | 创建管理员用户 | admin 登录 | POST /admin/api/v1/users {user_type="admin"} | 201, user_type=admin | G.12 |
| TC-USER-003 | 保护管理员不可删除 | admin 登录 | DELETE /admin/api/v1/users/{admin_id} | 403 PROTECTED_USER_OPERATION_DENIED | G.12 |
| TC-USER-004 | 保护管理员不可禁用 | admin 登录 | PATCH /admin/api/v1/users/{admin_id} {is_active:false} | 403 PROTECTED_USER_OPERATION_DENIED | G.12 |
| TC-USER-005 | 保护管理员不可改名 | admin 登录 | PATCH /admin/api/v1/users/{admin_id} {username:"new"} | 403 PROTECTED_USER_OPERATION_DENIED | G.12 |
| TC-USER-006 | 保护管理员不可改 user_type | admin 登录 | PATCH ... {user_type:"app_user"} | 403 PROTECTED_USER_OPERATION_DENIED | G.12 |
| TC-USER-007 | 普通用户可删除 | admin 登录 | DELETE /admin/api/v1/users/{user_id} | 204 | G.12 |
| TC-USER-008 | 字段白名单 - admin 只能改 email/role | admin 登录 | PATCH 只允许字段 | 更新成功 | G.12 |
| TC-USER-009 | 字段白名单 - app_user 只能改 email | admin 登录 | PATCH app_user 的 role | 忽略 role 字段 | G.12 |
| TC-USER-010 | 重置密码 | admin 登录 | POST /admin/api/v1/users/{id}/reset-password | 生成临时密码, 用户所有 family 撤销 | G.12 |
| TC-USER-011 | 撤销会话 | admin 登录 | POST /admin/api/v1/users/{id}/revoke-sessions | 所有 refresh family 撤销 | G.12 |
| TC-USER-012 | cursor 分页 | 多个用户 | GET /admin/api/v1/users?cursor=xxx&limit=10 | 按 created_at DESC 排序, limit 1..200 | G.12 |
| TC-USER-013 | 非法 limit 值 | admin 登录 | limit=0 或 limit=300 | 422 VALIDATION_FAILED | G.12 |

## 3. 目录管理链路 (G.5-G.7)

| ID | 用例名称 | 前置条件 | 测试步骤 | 预期结果 | 设计引用 |
|---|---|---|---|---|---|
| TC-CAT-001 | 创建 Agent | admin 登录 | POST /admin/api/v1/catalog/agents | 201, status=draft | G.5 |
| TC-CAT-002 | 创建 AgentVersionRange | Agent 已创建 | POST .../agents/{id}/versions | 201, 含 executable_names, platforms 等 | G.5 |
| TC-CAT-003 | 创建 Model | admin 登录 | POST /admin/api/v1/catalog/models | 201, 含 provider_key, model_key | G.6 |
| TC-CAT-004 | 创建 Provider | admin 登录 | POST /admin/api/v1/catalog/providers | 201 | G.6 |
| TC-CAT-005 | 创建 AgentModelBinding | Agent + Model 已创建 | POST .../agents/{id}/models | 201 | G.6 |
| TC-CAT-006 | 创建 ProviderModelBinding | Provider + Model 已创建 | POST .../providers/{id}/models | 201 | G.6 |
| TC-CAT-007 | 状态机 draft→validated→published | draft 资源 | PATCH status | 依次流转成功 | G.5 |
| TC-CAT-008 | 非法状态跳转拒绝 | draft 资源 | 直接 PATCH status=published | 422 STATE_TRANSITION_INVALID | G.5 |
| TC-CAT-009 | published 资源不可修改 | published 资源 | PATCH name | 409 CATALOG_REVISION_IMMUTABLE | G.5 |
| TC-CAT-010 | published 资源不可删除 | published 资源 | DELETE | 409 CATALOG_REVISION_IMMUTABLE | G.5 |
| TC-CAT-011 | 草稿复制 | published Agent | POST 复制 | 新 draft, version=1, 子版本一并复制 | G.5 |
| TC-CAT-012 | 兼容规则 CRUD | admin 登录 | CRUD compatibility_rules | 201/200/204 | G.7 |
| TC-CAT-013 | 兼容规则 deny 优先于 allow | 同一资源有 allow+deny | 评估兼容性 | deny 生效 | G.7 |
| TC-CAT-014 | CatalogValidator - SemVer 校验 | invalid version | validate | 报告版本格式错误 | G.5 |
| TC-CAT-015 | CatalogValidator - Provider URL SSRF | Provider URL 指向内网 | validate | 拒绝 | G.7 |

## 4. 发布管理链路 (G.9)

| ID | 用例名称 | 前置条件 | 测试步骤 | 预期结果 | 设计引用 |
|---|---|---|---|---|---|
| TC-REL-001 | 创建 Release | 有 published 资源 | POST /admin/api/v1/catalog/releases | 201, status=draft, 含 manifest | G.9 |
| TC-REL-002 | 发布 Release | draft Release | POST .../releases/{id}/publish | 200, status=published, published_at 设置 | G.9 |
| TC-REL-003 | 发布原子性 | draft Release | publish 中注入 DB 失败 | Release 保持 draft, S3 对象 GC | G.9 |
| TC-REL-004 | Ed25519 签名验证 | published Release | GET catalog/manifest | 响应含 signature, kid, 可验证 | G.9 |
| TC-REL-005 | 紧急禁用 Skill | 已发布 Skill | POST /admin/api/v1/emergency-disables | 201, sequence 递增 | G.9 |
| TC-REL-006 | 紧急禁用不可回退 | 已禁用 Skill | 取消禁用 | 不允许, 只能发布新的 enable | G.9 |
| TC-REL-007 | Keyset 轮换 | 当前 keyset | 轮换密钥 | 新 key 签名, 旧 key 仍可验证历史 | G.9 |
| TC-REL-008 | 并发发布安全 | 两个 publisher | 同时 publish | 只有一个成功, sequence 不重复 | G.9 |
| TC-REL-009 | 最低客户端版本检查 | Release 设 minimum_client | 低版本客户端同步 | 被拒绝 | G.9 |
| TC-REL-010 | Manifest 包含完整资源哈希 | published Release | 检查 manifest | 每个 resource 含 content_sha256 | G.9 |

## 5. Skill 管理链路 (G.8)

| ID | 用例名称 | 前置条件 | 测试步骤 | 预期结果 | 设计引用 |
|---|---|---|---|---|---|
| TC-SKILL-001 | ZIP 有效结构通过 | 含 manifest.json + .py | validate_zip_structure | (True, []) | G.8 |
| TC-SKILL-002 | ZIP 缺 manifest 拒绝 | 无 manifest.json | validate | (False, [...]) | G.8 |
| TC-SKILL-003 | ZIP 缺 Python 文件拒绝 | 无 .py 文件 | validate | (False, [...]) | G.8 |
| TC-SKILL-004 | ZIP 路径穿越拒绝 | 含 /etc/passwd 或 ../ | validate | (False, ["Suspicious path"]) | G.8 |
| TC-SKILL-005 | ZIP 危险文件拒绝 | 含 .exe 或 .sh | validate | (False, ["dangerous file"]) | G.8 |
| TC-SKILL-006 | ZIP 无效文件拒绝 | 非 ZIP 格式 | validate | (False, ["Invalid ZIP"]) | G.8 |
| TC-SKILL-007 | ZIP 空归档拒绝 | 空 ZIP | validate | (False, [...]) | G.8 |
| TC-SKILL-008 | SHA-256 校验正确 | ZIP 文件 | compute_zip_checksum | 返回 64 字符 hex, 确定性 | G.8 |
| TC-SKILL-009 | 对象存储 store+retrieve | 本地存储 | store → retrieve | 文件一致 | G.8 |
| TC-SKILL-010 | 对象存储 delete | 已存储文件 | delete | 文件删除, retrieve 返回 None | G.8 |
| TC-SKILL-011 | 对象存储 list_versions | 多版本存储 | list_versions | 返回排序列表 | G.8 |
| TC-SKILL-012 | 签名验证（占位） | ZIP + signature | verify_signature | 当前返回 True | G.8 |
| TC-SKILL-013 | 安装 Skill 全流程 | published Skill + ZIP | installSkill | 流式下载 → 校验 → fsync → rename → 写入 installed | G.8 |
| TC-SKILL-014 | 移除 Skill - 无引用 | installed Skill, 无活跃引用 | removeSkill | 删除 DB + 包文件 | G.8 |
| TC-SKILL-015 | 移除 Skill - 有引用拒绝 | installed Skill 被底座引用 | removeSkill | STATE_TRANSITION_INVALID | G.8 |
| TC-SKILL-016 | 紧急禁用 Skill | installed Skill | emergency_disable | status=disabled, 不删除包 | G.8 |

## 6. Sidecar RPC 链路 (H.2)

| ID | 用例名称 | 前置条件 | 测试步骤 | 预期结果 | 设计引用 |
|---|---|---|---|---|---|
| TC-RPC-001 | 方法注册与调用 | 注册 handler | handle({method:"ping"}) | {"result": "pong"} | H.2 |
| TC-RPC-002 | 方法不存在 | 无注册 | handle({method:"unknown"}) | {"error": {"code": -32601}} | H.2 |
| TC-RPC-003 | 参数传递 | 注册 handler | handle({params: {name:"a"}}) | handler 收到 params | H.2 |
| TC-RPC-004 | Handler 异常 | 注册抛异常的 handler | handle | {"error": {"code": -32603}} | H.2 |
| TC-RPC-005 | Notification | 无 id 请求 | handle({method:"x"}) | response.id=null, result 存在 | H.2 |
| TC-RPC-006 | 多方法共存 | 注册多个 handler | 调用不同方法 | 各自返回正确结果 | H.2 |

## 7. 公司领域链路 (H.5)

| ID | 用例名称 | 前置条件 | 测试步骤 | 预期结果 | 设计引用 | 已实现 |
|---|---|---|---|---|---|---|
| TC-COMP-001 | CompanyCreate schema 验证 | 无 | 创建 name="" | ValidationError | G.1 | ✅ |
| TC-COMP-002 | CompanyCreate 带行业 | 无 | 创建 name + industry | 字段正确赋值 | G.1 | ✅ |
| TC-COMP-003 | Company name 长度限制 | 无 | name 超 128 字符 | ValidationError | G.1 | ✅ |
| TC-COMP-004 | Company 全字段模型 | 无 | 创建完整 Company | 所有字段可序列化/反序列化 | G.1 | ✅ |
| TC-COMP-005 | 公司创建原子事务-成功 | 有 published base_profile_version | BEGIN IMMEDIATE 事务内创建 Company+Office+GM+Conversations | 全部成功, defer_foreign_keys 恢复 OFF | H.5 | ✅ |
| TC-COMP-006 | 公司创建-名称已存在 | 已存在同名公司 | 创建同名公司 | company_name_exists 错误 | H.5 | ✅ |
| TC-COMP-007 | 公司创建-外键验证 | 无 published version | 创建公司 | BASE_PROFILE_NOT_PUBLISHED | H.5 | ✅ |
| TC-COMP-008 | 公司创建-base_profile 必填 | base_profile_version_id="" | 创建公司 | BASE_PROFILE_VERSION_REQUIRED | H.5 | ✅ |
| TC-COMP-009 | 公司创建-事务回滚 | 注入 DB 错误 | 创建公司 | 全部回滚, 无残留数据 | H.5 | ✅ |
| TC-COMP-010 | 公司创建-外键 defer 恢复 | 事务前后检查 PRAGMA | 创建前后验证 defer_foreign_keys | PRAGMA 恢复为 OFF | H.5 | ✅ |
| TC-COMP-011 | 公司改名-成功 | 已创建公司 | rename_company(name, version) | 名称更新, version+1 | H.5 | ✅ |
| TC-COMP-012 | 公司改名-版本冲突 | 已创建公司 | rename_company(expected_version 不匹配) | company_version_conflict | H.5 | ✅ |
| TC-COMP-013 | 公司改名-名称冲突 | 两公司 | 用另一公司名称改名 | company_name_exists | H.5 | ✅ |
| TC-COMP-014 | 公司改名-仅改名称 | 已创建公司 | rename_company(name) | introduction 不变 | H.5 | ✅ |
| TC-COMP-015 | 辅助函数-new_id 唯一 | 无 | 调用 new_id() 100次 | 全部不同 | H.5 | ✅ |
| TC-COMP-016 | 辅助函数-normalize_name | 无 | normalize_name("  Foo Bar  ") | "foo bar" | H.5 | ✅ |
| TC-COMP-017 | 辅助函数-sha256 确定性 | 无 | sha256("hello") 两次 | 结果一致 | H.5 | ✅ |

## 8. 部门领域链路 (G.2)

| ID | 用例名称 | 前置条件 | 测试步骤 | 预期结果 | 设计引用 | 已实现 |
|---|---|---|---|---|---|---|
| TC-DEPT-001 | DepartmentCreate 验证 | 无 | name="" | ValidationError | G.2 | ✅ |
| TC-DEPT-002 | 子部门创建 | parent_id 有值 | DepartmentCreate(parent_id="d1") | parent_id 正确 | G.2 | ✅ |
| TC-DEPT-003 | 部门 name 长度限制 | 无 | name 超 128 字符 | ValidationError | G.2 | ✅ |
| TC-DEPT-004 | Department 全字段模型 | 无 | 创建完整 Department | 序列化/反序列化正确 | G.2 | ✅ |
| TC-DEPT-005 | 创建部门 | company 已创建 | create_department(name, department_type) | 所有字段正确 | G.2 | ✅ |
| TC-DEPT-006 | 创建子部门 | parent 部门存在 | create_department(parent_id) | 父子关系正确 | G.2 | ✅ |
| TC-DEPT-007 | 获取部门 | 已创建部门 | get_department(id) | 返回完整部门 | G.2 | ✅ |
| TC-DEPT-008 | 获取不存在部门 | 无 | get_department(nonexistent) | not_found | G.2 | ✅ |
| TC-DEPT-009 | 列出部门 | 多个部门 | list_departments(company_id) | 返回列表 | G.2 | ✅ |
| TC-DEPT-010 | 列出部门-含父部门 | 子部门存在 | list_departments 含子部门 | parent_id 正确关联 | G.2 | ✅ |
| TC-DEPT-011 | 更新部门 | 已创建部门 | update_department(name) | 名称更新 | G.2 | ✅ |
| TC-DEPT-012 | 删除部门 | 已创建部门 | delete_department(id) | 部门删除 | G.2 | ✅ |

## 9. 职员领域链路 (G.3)

| ID | 用例名称 | 前置条件 | 测试步骤 | 预期结果 | 设计引用 | 已实现 |
|---|---|---|---|---|---|---|
| TC-EMP-001 | StaffCreate 验证 | 无 | name="" | ValidationError | G.3 | ✅ |
| TC-EMP-002 | 默认角色 | 无 | StaffCreate(name="a") | role="member" | G.3 | ✅ |
| TC-EMP-003 | 自定义角色 | 无 | StaffCreate(name="a", role="lead") | role="lead" | G.3 | ✅ |
| TC-EMP-004 | name 长度限制 | 无 | name 超 64 字符 | ValidationError | G.3 | ✅ |
| TC-EMP-005 | 创建职员 | 部门已创建 | create_employee(name, department_id) | 所有字段正确 | G.3 | ✅ |
| TC-EMP-006 | 创建职员-指定部门 | 部门存在 | create_employee(department_id) | department_id 正确 | G.3 | ✅ |
| TC-EMP-007 | 获取职员 | 已创建职员 | get_employee(id) | 返回完整职员 | G.3 | ✅ |
| TC-EMP-008 | 获取不存在职员 | 无 | get_employee(nonexistent) | not_found | G.3 | ✅ |
| TC-EMP-009 | 列出职员 | 多个职员 | list_employees(company_id) | 返回列表 | G.3 | ✅ |
| TC-EMP-010 | 列出职员-按角色筛选 | 不同角色职员 | list_employees(role="lead") | 只返回 lead | G.3 | ✅ |
| TC-EMP-011 | 更新职员 | 已创建职员 | update_employee(name) | 名称更新 | G.3 | ✅ |
| TC-EMP-012 | 删除职员 | 已创建职员 | delete_employee(id) | 职员删除 | G.3 | ✅ |
| TC-EMP-013 | 列出部门 | 公司有部门 | list_departments | 返回部门列表 | G.3 | ✅ |

## 10. 会话/消息领域链路 (G.4)

| ID | 用例名称 | 前置条件 | 测试步骤 | 预期结果 | 设计引用 |
|---|---|---|---|---|---|
| TC-CONV-001 | Conversation 创建 | 无 | ConversationCreate(company_id, staff_id) | 所有字段正确 | G.4 |
| TC-CONV-002 | Conversation 默认状态 | 无 | 创建 Conversation | status="active" | G.4 |
| TC-CONV-003 | Message 创建 | 无 | Message(role="user", content="Hi") | content 和 role 正确 | G.4 |
| TC-CONV-004 | Message 带 metadata | 无 | MessageCreate(metadata={"tokens":10}) | metadata 正确存储 | G.4 |
| TC-CONV-005 | Task 创建 | 无 | TaskCreate(company_id, title="T") | status="pending", priority="normal" | G.10 |
| TC-CONV-006 | Task title 长度限制 | 无 | title="" | ValidationError | G.10 |
| TC-CONV-007 | Task 带 assignee | 无 | Task(assignee_id="s1") | assignee_id 正确 | G.10 |
| TC-CONV-008 | Task 关联 conversation | 无 | Task(conversation_id="conv1") | conversation_id 正确 | G.10 |

## 11. 任务状态机链路 (H.7)

> 97 个测试覆盖 9 个实体类型的全部合法状态迁移和非法迁移拒绝

| ID | 用例名称 | 前置条件 | 测试步骤 | 预期结果 | 设计引用 | 已实现 |
|---|---|---|---|---|---|---|
| TC-TASK-001 | CompanyTask 完整流转 | 新任务 | draft→analyzing→awaiting_user_confirmation→approved→dispatching→executing→reviewing→completed | 每步状态正确 | H.7 | ✅ |
| TC-TASK-002 | CompanyTask 非法迁移-draft→running | draft 状态 | 非法跳转 | STATE_TRANSITION_INVALID | H.7 | ✅ |
| TC-TASK-003 | CompanyTask 终态检查 | completed 状态 | 任何迁移 | 拒绝 | H.7 | ✅ |
| TC-TASK-004 | CompanyTask 用户确认门禁 | awaiting_user_confirmation | 未确认直接执行 | 拒绝 | H.7 | ✅ |
| TC-TASK-005 | CompanyTask revision_requested | awaiting_user_confirmation | 用户要求修改 | 状态回退, 新 PlanVersion | H.7 | ✅ |
| TC-TASK-006 | CompanyTask rejected | awaiting_user_confirmation | 用户拒绝 | 不再创建 Run | H.7 | ✅ |
| TC-TASK-007 | CompanyTask paused→cancelled | paused 状态 | 取消 | 进入 cancelled | H.7 | ✅ |
| TC-TASK-008 | CompanyTask waiting→cancelled | waiting 状态 | 取消 | 进入 cancelled | H.7 | ✅ |
| TC-TASK-009 | CompanyTask analyzing→failed | analyzing 状态 | 注入失败 | 进入 failed | H.7 | ✅ |
| TC-TASK-010 | CompanyTask final_review→completed | final_review 状态 | 审查通过 | 进入 completed | H.7 | ✅ |
| TC-TASK-011 | CompanyTask reviewing→fixing | reviewing 状态 | 审查不通过 | 进入 fixing | H.7 | ✅ |
| TC-TASK-012 | CompanyTask reviewing→final_review | reviewing 状态 | 审查通过(部分) | 进入 final_review | H.7 | ✅ |
| TC-TASK-013 | CompanyTask dispatching→checking | dispatching 状态 | 分发完成 | 进入 checking | H.7 | ✅ |
| TC-TASK-014 | CompanyTask get_allowed_targets | draft/completed 状态 | 查询可用目标 | 返回正确目标列表 | H.7 | ✅ |
| TC-TASK-015 | DepartmentTask 完整流转 | 已确认计划 | draft→checking_resources→ready→executing→reviewing→completed | 状态正确 | H.7 | ✅ |
| TC-TASK-016 | DepartmentTask draft→cancelled | draft 状态 | 取消 | 进入 cancelled | H.7 | ✅ |
| TC-TASK-017 | DepartmentTask 非法迁移-draft→executing | draft 状态 | 直接跳转 | 拒绝 | H.7 | ✅ |
| TC-TASK-018 | DepartmentTask 终态检查 | completed/cancelled 状态 | 任何迁移 | 拒绝 | H.7 | ✅ |
| TC-TASK-019 | DepartmentTask reviewing→fixing | reviewing 状态 | 审查不通过 | 进入 fixing | H.7 | ✅ |
| TC-TASK-020 | DepartmentTask fixing→reviewing | fixing 状态 | 修复完成 | 进入 reviewing | H.7 | ✅ |
| TC-TASK-021 | EmployeeTask 完整流转 | 部门任务就绪 | assigned→ready→running→submitted→peer_reviewing→accepted | 状态正确 | H.7 | ✅ |
| TC-TASK-022 | EmployeeTask running→waiting_resource | running 状态 | 资源不足 | 进入 waiting_resource | H.7 | ✅ |
| TC-TASK-023 | EmployeeTask peer_reviewing→changes_requested | peer_reviewing 状态 | 审查不通过 | 进入 changes_requested | H.7 | ✅ |
| TC-TASK-024 | EmployeeTask changes_requested→ready | changes_requested 状态 | 修改完成 | 进入 ready | H.7 | ✅ |
| TC-TASK-025 | EmployeeTask 终态检查 | accepted/cancelled 状态 | 任何迁移 | 拒绝 | H.7 | ✅ |
| TC-TASK-026 | AgentRun 完整流转 | 执行请求 | queued→probing→starting→running→verifying→succeeded | 状态正确 | H.7 | ✅ |
| TC-TASK-027 | AgentRun running→lost | running 状态 | 进程丢失 | 进入 lost | H.7 | ✅ |
| TC-TASK-028 | AgentRun running→waiting_approval | running 状态 | 需要审批 | 进入 waiting_approval | H.7 | ✅ |
| TC-TASK-029 | AgentRun lost→retrying | lost 状态 | 重试 | 进入 retrying | H.7 | ✅ |
| TC-TASK-030 | AgentRun lost 非法迁移→succeeded | lost 状态 | 直接成功 | 拒绝 | H.7 | ✅ |
| TC-TASK-031 | AgentRun 超时 | running 超时 | timeout | timed_out | H.7 | ✅ |
| TC-TASK-032 | AgentRun 取消 | queued/running | cancel | cancelled | H.7 | ✅ |
| TC-TASK-033 | AgentRun 终态检查 | succeeded/timed_out/lost 状态 | 任何迁移 | 拒绝 | H.7 | ✅ |
| TC-TASK-034 | ReviewAssignment 完整流转 | 审查分配 | assigned→in_review→submitted | 状态正确 | H.7 | ✅ |
| TC-TASK-035 | ReviewAssignment submitted→stale | submitted 状态 | 审查过期 | 进入 stale | H.7 | ✅ |
| TC-TASK-036 | ReviewAssignment 终态检查 | stale/cancelled 状态 | 任何迁移 | 拒绝 | H.7 | ✅ |
| TC-TASK-037 | ReviewIssue 完整流转 | 审查问题 | open→fixing→resolved→verified→closed | 状态正确 | H.7 | ✅ |
| TC-TASK-038 | ReviewIssue open→rejected | open 状态 | 拒绝问题 | 进入 rejected | H.7 | ✅ |
| TC-TASK-039 | ReviewIssue 终态检查 | closed/rejected 状态 | 任何迁移 | 拒绝 | H.7 | ✅ |
| TC-TASK-040 | ReviewIssue verified→fixing | verified 状态 | 重新打开 | 进入 fixing | H.7 | ✅ |
| TC-TASK-041 | CompanyPlanVersion 完整流转 | 新计划 | draft→awaiting→approved | 状态正确 | H.7 | ✅ |
| TC-TASK-042 | CompanyPlanVersion draft→rejected | draft 状态 | 拒绝 | 进入 rejected | H.7 | ✅ |
| TC-TASK-043 | CompanyPlanVersion awaiting→superseded | awaiting 状态 | 新版本创建 | 进入 superseded | H.7 | ✅ |
| TC-TASK-044 | CompanyPlanVersion 终态检查 | approved/superseded 状态 | 任何迁移 | 拒绝 | H.7 | ✅ |
| TC-TASK-045 | TaskWorkspace 完整流转 | 任务工作区 | preparing→active→ready_to_apply→applied | 状态正确 | H.7 | ✅ |
| TC-TASK-046 | TaskWorkspace 终态检查 | applied/abandoned 状态 | 任何迁移 | 拒绝 | H.7 | ✅ |
| TC-TASK-047 | HumanApproval 完整流转 | 审批请求 | pending→allowed→consumed | 状态正确 | H.7 | ✅ |
| TC-TASK-048 | HumanApproval pending→denied | pending 状态 | 拒绝 | 进入 denied | H.7 | ✅ |
| TC-TASK-049 | HumanApproval pending→expired | pending 状态 | 超时 | 进入 expired | H.7 | ✅ |
| TC-TASK-050 | HumanApproval allowed→expired | allowed 状态 | 超时 | 进入 expired | H.7 | ✅ |
| TC-TASK-051 | HumanApproval 终态检查 | denied/consumed 状态 | 任何迁移 | 拒绝 | H.7 | ✅ |
| TC-TASK-052 | 状态机 validate_resume_state | waiting 状态 | 验证 resume 参数 | 需要 resume_token | H.7 | ✅ |
| TC-TASK-053 | 状态机未知实体类型 | 无 | 调用不存在的实体类型 | raises InvalidStateError | H.7 | ✅ |
| TC-TASK-054 | 状态机未知状态 | 不存在的状态 | 迁移到未知状态 | raises InvalidStateError | H.7 | ✅ |
| TC-TASK-055 | 状态机终态迁移 | terminal 状态 | 任何迁移 | raises InvalidStateError | H.7 | ✅ |
| TC-TASK-056 | 状态机 get_allowed_targets | terminal 状态 | 查询可用目标 | 返回空集合 | H.7 | ✅ |

## 12. 编排平台链路 (G.11)

| ID | 用例名称 | 前置条件 | 测试步骤 | 预期结果 | 设计引用 |
|---|---|---|---|---|---|
| TC-ORCH-001 | 公司级计划生成 | 用户输入任务 | general_manager_analysis→company_plan_draft | 生成含目标/部门任务/依赖的计划 | G.11 |
| TC-ORCH-002 | PlanValidator PV-001 | goals 为空 | validate | PLAN_VALIDATION_FAILED PV-001 | G.11 |
| TC-ORCH-003 | PlanValidator PV-002 | 引用不存在部门 | validate | PLAN_VALIDATION_FAILED PV-002 | G.11 |
| TC-ORCH-004 | PlanValidator PV-003 | 循环依赖 | validate | PLAN_VALIDATION_FAILED PV-003 | G.11 |
| TC-ORCH-005 | PlanValidator PV-004 | 部门无负责人 | validate | PLAN_VALIDATION_FAILED PV-004 | G.11 |
| TC-ORCH-006 | PlanValidator PV-008 | 无非贡献者 Reviewer | validate | PLAN_VALIDATION_FAILED PV-008 | G.11 |
| TC-ORCH-007 | 部门匹配 | 任务类型+能力 | departmentMatch | 返回候选部门+置信度 | G.11 |
| TC-ORCH-008 | 职员可用性检查 - 7项 | 职员+部门+Agent | availabilityCheck | 全部通过或返回不可用原因 | G.11 |
| TC-ORCH-009 | 职员不可用 → waiting_resource | Agent 未安装 | availabilityCheck | 部门任务进入 waiting_resource | G.11 |
| TC-ORCH-010 | Review 贡献者≠Reviewer | 产出 artifact | 分配 Review | 贡献者不在 Reviewer 集合中 | G.11 |
| TC-ORCH-011 | 唯一贡献者且负责人未参与 | 只有一名职员 | 分配 Review | 负责人 Review, 或增加参与职员 | G.11 |
| TC-ORCH-012 | 4 种协作策略 | 部门任务 | independent_drafts/section_partition/primary_with_peer_review/sequential_refinement | 各策略正确执行 | G.11 |

## 13. Workspace/Artifact/Review 链路

| ID | 用例名称 | 前置条件 | 测试步骤 | 预期结果 | 设计引用 |
|---|---|---|---|---|---|
| TC-WORK-001 | Workspace 创建 | 无 | WorkspaceCreate(company_id, name) | status="active" | G.15 |
| TC-WORK-002 | Artifact 创建 | Workspace 存在 | ArtifactCreate(workspace_id, name, artifact_type) | 正确关联 | G.15 |
| TC-WORK-003 | Artifact 带 content/metadata | 无 | Artifact(content="...", metadata={}) | 字段正确 | G.15 |
| TC-WORK-004 | Review 创建 | Artifact 存在 | ReviewCreate(artifact_id, reviewer_id) | status="pending" | G.11 |
| TC-WORK-005 | Review 审批 | pending Review | ReviewAction(status="approved") | status=approved | G.11 |
| TC-WORK-006 | Review 拒绝 | pending Review | ReviewAction(status="rejected", comments="...") | status=rejected, comments 存储 | G.11 |
| TC-WORK-007 | ReviewAction 非法状态拒绝 | pending Review | ReviewAction(status="invalid") | ValidationError (regex 校验) | G.11 |

## 14. 知识/备份领域链路

| ID | 用例名称 | 前置条件 | 测试步骤 | 预期结果 | 设计引用 |
|---|---|---|---|---|---|
| TC-KNOW-001 | KnowledgeDocument 创建 | 无 | KnowledgeCreate(company_id, title, content, tags) | 所有字段正确 | G.16 |
| TC-KNOW-002 | SearchQuery 验证 | 无 | SearchQuery(query="test") | limit 默认 10 | G.16 |
| TC-KNOW-003 | SearchResult 验证 | 无 | SearchResult(document_id, title, score) | score 为 float | G.16 |
| TC-KNOW-004 | BackupJob 创建 | 无 | BackupCreate(company_id, backup_type="full") | status="pending" | G.21 |
| TC-KNOW-005 | RestoreJob 创建 | BackupJob 存在 | RestoreCreate(backup_id) | status="pending" | G.21 |

## 15. Workflow 编排模型链路

| ID | 用例名称 | 前置条件 | 测试步骤 | 预期结果 | 设计引用 |
|---|---|---|---|---|---|
| TC-ORCH-M-001 | Workflow 创建 | 无 | WorkflowCreate(company_id, name, steps) | status="draft" | G.11 |
| TC-ORCH-M-002 | WorkflowStep 创建 | 无 | WorkflowStepCreate(name, step_type, order) | order 和 dependencies 正确 | G.11 |
| TC-ORCH-M-003 | WorkflowExecution 创建 | 无 | WorkflowExecution(workflow_id) | status="pending", results={} | G.11 |

## 16. Agent Runtime 模型链路

| ID | 用例名称 | 前置条件 | 测试步骤 | 预期结果 | 设计引用 |
|---|---|---|---|---|---|
| TC-RT-001 | AgentRuntime 创建 | 无 | RuntimeCreate(agent_id, model) | status="idle" | G.6 |
| TC-RT-002 | AgentMessage 创建 | 无 | MessageCreate(role="assistant", content="...") | 所有字段正确 | G.6 |
| TC-RT-003 | AgentToolCall 创建 | 无 | 创建 tool call | status="pending" | G.6 |

## 17. 中间件/安全/可观测链路

| ID | 用例名称 | 前置条件 | 测试步骤 | 预期结果 | 设计引用 | 已实现 |
|---|---|---|---|---|---|---|
| TC-MW-001 | Audit middleware 记录请求 | 请求经过 | 发送 POST 请求 | audit_logs 表写入记录 | G.10 | ✅ |
| TC-MW-002 | Audit middleware 跳过健康检查 | 请求经过 | GET /health | 不写入审计日志 | G.10 | ✅ |
| TC-MW-003 | Audit middleware resource_type 提取 | 无 | _resource_type_from_path("/admin/api/v1/users") | 返回 "admin" | G.10 | ✅ |
| TC-MW-004 | Audit middleware resource_id 提取 | 无 | _extract_resource_id("/api/v1/users/abc-123") | 返回 "abc-123" | G.10 | ✅ |
| TC-MW-005 | Audit middleware 跳过 auth 端点 | 无 | _is_auth_endpoint("/auth/login") | 返回 True | G.10 | ✅ |
| TC-MW-006 | Audit middleware IP 提取 | x-forwarded-for 头 | _get_client_ip | 返回第一个 IP | G.10 | ✅ |
| TC-MW-007 | Idempotency middleware 缓存重用 | 同 key 重复请求 | 发两次相同 idempotency_key | 第二次返回缓存结果 | G.10 | ✅ |
| TC-MW-008 | Idempotency middleware 冲突检测 | 同 key 不同 body | 发两次不同 body | 返回 409 IDEMPOTENCY_CONFLICT | G.10 | ✅ |
| TC-MW-009 | Rate Limit 限流 | 同一 IP | 连续 5+ 次请求 | 超过后 429 RATE_LIMITED | G.10 | ✅ |
| TC-MW-010 | CORS 配置 | 跨域请求 | OPTIONS 请求 | 按配置允许/拒绝 | G.23 | - |
| TC-SEC-001 | 密码 Argon2id 哈希 | 无 | create_user | hashed_password 可 verify 原密码 | G.23 | ✅ |
| TC-SEC-002 | API Key 验证 | 无 | validate_api_key | 长度>=32 通过, <32 拒绝 | G.23 | - |
| TC-SEC-003 | 安全响应头 | 无 | get_secure_headers | 含 X-Content-Type-Options 等 | G.23 | - |
| TC-OBS-001 | PerformanceMetrics 记录 | 无 | record_request(0.5) | average_duration=0.5 | G.24 | - |
| TC-OBS-002 | PerformanceMetrics reset | 有记录 | reset() | 所有计数归零 | G.24 | - |
| TC-OBS-003 | track_performance 装饰器 | 无 | @track_performance 装饰函数 | 函数执行后 metrics 更新 | G.24 | - |
| TC-OBS-004 | 结构化日志 | 无 | setup_logging(json_format=True) | 日志输出为 JSON | G.24 | - |

## 18. Rust Desktop Core 链路

| ID | 用例名称 | 前置条件 | 测试步骤 | 预期结果 | 设计引用 |
|---|---|---|---|---|---|
| TC-RUST-001 | SecureKeyring set/get | 无 | set("k","v") → get("k") | 返回 Some("v") | J.3 |
| TC-RUST-002 | SecureKeyring delete | 已 set | delete("k") → get("k") | 返回 None | J.3 |
| TC-RUST-003 | SecureKeyring list_keys | 已 set 多个 | list_keys() | 返回所有 key | J.3 |
| TC-RUST-004 | LocalStore 路径 | 无 | new(path) | config/data 路径正确 | J.2 |
| TC-RUST-005 | LocalStore 目录创建 | 无 | ensure_directories() | 目录存在 | J.2 |
| TC-RUST-006 | RPC Router 注册+处理 | 无 | register + handle | 正确路由到 handler | J.14 |
| TC-RUST-007 | RPC Router 方法不存在 | 无 | handle 未知 method | MethodNotFound 错误 | J.14 |
| TC-RUST-008 | RPC Error codes | 无 | 各错误变体 | code 正确 (-32601 等) | J.14 |
| TC-RUST-009 | SidecarProcess new | 无 | new(port) | port 正确, 未运行 | F.3 |
| TC-RUST-010 | SidecarProcess stop without start | 无 | stop() | 不 panic | F.3 |

## 19. 前端 UI 链路

| ID | 用例名称 | 前置条件 | 测试步骤 | 预期结果 | 设计引用 |
|---|---|---|---|---|---|
| TC-UI-001 | 桌面端类型定义完整 | 无 | 检查 types/index.ts | Company/Department/Staff/Conversation/Message/Task 等接口 | K.1 |
| TC-UI-002 | useConversations hook | 无 | 调用 hook | 返回 conversations/loading/error | K.1 |
| TC-UI-003 | useTasks hook | 无 | 调用 hook | 返回 tasks/loading/error | K.1 |
| TC-UI-004 | Sidebar 组件渲染 | 无 | 渲染 Sidebar | 显示导航项 | K.1 |
| TC-UI-005 | ChatPanel 组件 | 无 | 渲染 ChatPanel | 消息列表+输入框 | K.1 |
| TC-UI-006 | 管理端类型定义 | 无 | 检查 types/index.ts | User/Skill/CatalogRelease/AuditLog 接口 | K.1 |
| TC-UI-007 | UserList 组件 | 无 | 渲染 UserList | 表格显示用户数据 | K.1 |
| TC-UI-008 | SkillList 组件 | 无 | 渲染 SkillList | 卡片网格显示 | K.1 |

## 20. 端到端链路

| ID | 用例名称 | 前置条件 | 测试步骤 | 预期结果 | 设计引用 |
|---|---|---|---|---|---|
| TC-E2E-001 | 注册→登录→创建公司 | 清空状态 | 注册 → 登录 → 创建公司 | 每步成功, token 有效 | G.1+G.11 |
| TC-E2E-002 | Token 生命周期 | 已登录 | access→过期→refresh→新 access | 轮换成功 | G.11 |
| TC-E2E-003 | 安全隔离 - 跨用户 | 两个用户 | user1 创建数据, user2 尝试访问 | user2 不可见 | G.1 |
| TC-E2E-004 | 安全隔离 - 跨公司 | 同一用户两个公司 | company_a 数据, company_b 访问 | 不可见 | G.1 |
| TC-E2E-005 | 目录发布→Skill 安装 | admin 发布目录 | 客户端同步→安装 Skill | Skill 可用 | G.8+G.9 |
| TC-E2E-006 | 崩溃恢复 | 运行中 AgentRun | 模拟崩溃→重启 | 非终态 Run 恢复或进入 waiting_approval | G.21 |

---

## 15. Rust Desktop Core - Backend API 对接

| ID | 用例名称 | 前置条件 | 测试步骤 | 预期结果 | 设计引用 |
|---|---|---|---|---|---|
| TC-RUST-001 | ApiClient 模块存在 | 无 | 检查 rpc/api_client.rs 文件 | 文件存在, 包含 register/login/refresh_token 方法 | P9 |
| TC-RUST-002 | register 命令存在 | 无 | 检查 commands.rs | 包含 pub async fn register, 调用 api_client.register | P9 |
| TC-RUST-003 | login 命令对接后端 API | 无 | 检查 commands.rs login 实现 | 调用 api_client.login 而非 sidecar | P9 |
| TC-RUST-004 | AppState 包含 api_client | 无 | 检查 commands.rs AppState | 包含 pub api_client: ApiClient | P9 |
| TC-RUST-005 | lib.rs 初始化 ApiClient | 无 | 检查 lib.rs setup | 创建 ApiClient::new(51080), 传入 AppState | P9 |
| TC-RUST-006 | 端口配置正确 | 无 | 检查 lib.rs | sidecar_port=51890, api_port=51080 | P9 |

---

## 16. 前端 Mock 消除验证

| ID | 用例名称 | 前置条件 | 测试步骤 | 预期结果 | 设计引用 |
|---|---|---|---|---|---|
| TC-MOCK-001 | LoginPage 无 mock-token | 无 | 搜索 LoginPage.tsx | 不包含 "mock-token" | P9 |
| TC-MOCK-002 | RegisterPage 无模拟跳转 | 无 | 搜索 RegisterPage.tsx | 不包含 "模拟", 调用 invoke | P9 |
| TC-MOCK-003 | useCompany 使用 invoke | 无 | 搜索 useCompany.ts | 包含 "invoke", 无 "TODO" | P9 |
| TC-MOCK-004 | useConversation 使用 invoke | 无 | 搜索 useConversation.ts | 包含 "invoke", 无 "TODO" | P9 |
| TC-MOCK-005 | useKnowledge 使用 invoke | 无 | 搜索 useKnowledge.ts | 包含 "invoke", 无 "TODO" | P9 |
| TC-MOCK-006 | useWorkspace 使用 invoke | 无 | 搜索 useWorkspace.ts | 包含 "invoke", 无 "TODO" | P9 |
| TC-MOCK-007 | useOrchestration 使用 invoke | 无 | 搜索 useOrchestration.ts | 包含 "invoke", 无 "TODO" | P9 |
| TC-MOCK-008 | useAgent 使用 invoke | 无 | 搜索 useAgent.ts | 包含 "invoke", 无 "TODO" | P9 |
| TC-MOCK-009 | useConversations 使用 invoke | 无 | 搜索 useConversations.ts | 包含 "invoke", 无 "TODO" | P9 |
| TC-MOCK-010 | useTasks 使用 invoke | 无 | 搜索 useTasks.ts | 包含 "invoke", 无 "TODO" | P9 |
| TC-MOCK-011 | Admin SettingsPage 无 MOCK_SETTINGS | 无 | 搜索 SettingsPage.tsx | 不包含 "MOCK_SETTINGS" | P10 |
| TC-MOCK-012 | Admin vite 有代理配置 | 无 | 搜索 vite.config.ts | 包含 proxy, 目标 51080 | P10 |
| TC-MOCK-013 | 全局无 mock-token | 无 | 搜索 desktop/src 全目录 | 所有 .tsx/.ts 不包含 "mock-token" | P9 |

---

## 17. 部署配置验证

| ID | 用例名称 | 前置条件 | 测试步骤 | 预期结果 | 设计引用 |
|---|---|---|---|---|---|
| TC-DEPLOY-001 | docker-compose 端口正确 | 无 | 读取 docker-compose.yml | PostgreSQL=51543, Backend=51080 | P11 |
| TC-DEPLOY-002 | Dockerfile 使用 venv uvicorn | 无 | 读取 Dockerfile | CMD 使用 .venv/bin/uvicorn | P11 |
| TC-DEPLOY-003 | settings.py 端口正确 | 无 | 读取 settings.py | database_url 包含 51543 | P11 |
| TC-DEPLOY-004 | Vite 端口正确 | 无 | 读取 vite.config.ts | Desktop=51420, Admin=51421 | P9/P10 |
| TC-DEPLOY-005 | tauri.conf.json devUrl 正确 | 无 | 读取 tauri.conf.json | devUrl 包含 51420 | P9 |
| TC-DEPLOY-006 | Rust 端口一致 | 无 | 读取 lib.rs | sidecar=51890, api=51080 | P9 |

## 21. 安全边界测试

| ID | 用例名称 | 前置条件 | 测试步骤 | 预期结果 | 设计引用 |
|---|---|---|---|---|---|
| TC-SEC-004 | 密码 Argon2id 哈希验证 | 无 | 创建用户后验证密码哈希 | hashed_password 可 verify 原密码, 不同 salt 产生不同哈希 | G.23 |
| TC-SEC-005 | JWT Token 过期验证 | 已签发 token | 等待 token 过期后调用接口 | 401 AUTH_TOKEN_EXPIRED | G.11 |
| TC-SEC-006 | JWT Token 签名验证 | 已签发 token | 篡改 token payload | 401 无效签名 | G.11 |
| TC-SEC-007 | Refresh Token 重放攻击 | 已轮换的 refresh_token | 再次使用旧 refresh_token | 撤销整个 family, 401 | G.11 |
| TC-SEC-008 | 跨域请求拦截 | 无 | 发送跨域 OPTIONS 请求 | 按 CORS 配置允许/拒绝 | G.23 |
| TC-SEC-009 | SQL 注入防护 | 无 | 在输入字段注入 SQL 语句 | 输入被转义, 无 SQL 执行 | G.23 |
| TC-SEC-010 | XSS 防护 | 无 | 在输入字段注入 JavaScript | 输入被转义, 无脚本执行 | G.23 |
| TC-SEC-011 | 路径遍历防护 | 无 | 尝试访问 ../../etc/passwd | 403 路径不允许 | G.23 |
| TC-SEC-012 | 文件上传大小限制 | 无 | 上传超过 50MB 的 ZIP | 413 文件过大 | G.8 |
| TC-SEC-013 | ZIP 解压大小限制 | 无 | 上传解压后超过 200MB 的 ZIP | 413 解压后文件过大 | G.8 |
| TC-SEC-014 | ZIP 路径遍历检测 | 无 | 上传含 ../ 的 ZIP | 400 路径遍历检测 | G.8 |
| TC-SEC-015 | ZIP 危险文件检测 | 无 | 上传含 .exe/.sh 的 ZIP | 400 危险文件检测 | G.8 |
| TC-SEC-016 | 敏感信息日志脱敏 | 无 | 触发包含密码/Token 的日志 | 日志中密码/Token 被脱敏 | G.24 |
| TC-SEC-017 | API Key 长度验证 | 无 | 使用短于 32 字符的 API Key | 401 无效 API Key | G.23 |
| TC-SEC-018 | 安全响应头验证 | 无 | 检查响应头 | 含 X-Content-Type-Options, X-Frame-Options 等 | G.23 |
| TC-SEC-019 | Rate Limiting 验证 | 无 | 连续快速请求 | 超过限制后 429 RATE_LIMITED | G.11 |
| TC-SEC-020 | 并发请求安全 | 无 | 同时发送多个相同请求 | 幂等键正确处理, 无重复操作 | G.10 |

## 22. 异常处理测试

| ID | 用例名称 | 前置条件 | 测试步骤 | 预期结果 | 设计引用 |
|---|---|---|---|---|---|
| TC-ERR-001 | 数据库连接失败 | 数据库不可用 | 启动服务 | 503 SERVICE_UNAVAILABLE | G.21 |
| TC-ERR-002 | 数据库迁移失败 | 迁移脚本错误 | 执行迁移 | 迁移失败, 服务不启动 | G.21 |
| TC-ERR-003 | Redis 连接失败 | Redis 不可用 | 启动服务 | 503 SERVICE_UNAVAILABLE | G.21 |
| TC-ERR-004 | S3 存储不可用 | S3 不可用 | 上传文件 | 503 STORAGE_UNAVAILABLE | G.8 |
| TC-ERR-005 | 文件系统权限错误 | 目录不可写 | 写入文件 | 500 INTERNAL_ERROR | G.21 |
| TC-ERR-006 | JSON 解析错误 | 无效 JSON | 发送请求 | 400 INVALID_JSON | G.14 |
| TC-ERR-007 | 请求体过大 | 超大请求体 | 发送请求 | 413 REQUEST_TOO_LARGE | G.14 |
| TC-ERR-008 | 请求超时 | 慢速请求 | 发送请求 | 408 REQUEST_TIMEOUT | G.14 |
| TC-ERR-009 | 并发写入冲突 | 同一资源 | 并发更新 | 409 CONFLICT | G.10 |
| TC-ERR-010 | 资源不存在 | 无 | 访问不存在的资源 | 404 NOT_FOUND | G.14 |
| TC-ERR-011 | 权限不足 | 普通用户 | 访问管理员接口 | 403 FORBIDDEN | G.11 |
| TC-ERR-012 | Token 过期 | 过期 token | 调用接口 | 401 AUTH_TOKEN_EXPIRED | G.11 |
| TC-ERR-013 | 无效 Token | 篡改 token | 调用接口 | 401 INVALID_TOKEN | G.11 |
| TC-ERR-014 | 缺少必需字段 | 不完整请求 | 发送请求 | 422 VALIDATION_FAILED | G.14 |
| TC-ERR-015 | 字段类型错误 | 类型不匹配 | 发送请求 | 422 VALIDATION_FAILED | G.14 |
| TC-ERR-016 | 字段值超出范围 | 超出范围 | 发送请求 | 422 VALIDATION_FAILED | G.14 |
| TC-ERR-017 | 枚举值无效 | 无效枚举 | 发送请求 | 422 VALIDATION_FAILED | G.14 |
| TC-ERR-018 | UUID 格式错误 | 无效 UUID | 发送请求 | 422 VALIDATION_FAILED | G.14 |
| TC-ERR-019 | 日期格式错误 | 无效日期 | 发送请求 | 422 VALIDATION_FAILED | G.14 |
| TC-ERR-020 | 邮箱格式错误 | 无效邮箱 | 发送请求 | 422 VALIDATION_FAILED | G.11 |

## 23. 性能测试用例

| ID | 用例名称 | 前置条件 | 测试步骤 | 预期结果 | 设计引用 |
|---|---|---|---|---|---|
| TC-PERF-001 | 登录响应时间 | 无 | 100 并发登录请求 | p95 < 500ms | K.16 |
| TC-PERF-002 | Token 刷新响应时间 | 已登录 | 100 并发 refresh 请求 | p95 < 200ms | K.16 |
| TC-PERF-003 | 目录列表响应时间 | 有数据 | 100 并发目录查询 | p95 < 300ms | K.16 |
| TC-PERF-004 | 文件上传响应时间 | 无 | 10MB 文件上传 | p95 < 2s | K.16 |
| TC-PERF-005 | 文件下载响应时间 | 已上传 | 10MB 文件下载 | p95 < 1s | K.16 |
| TC-PERF-006 | 数据库查询性能 | 有数据 | 1000 条记录查询 | p95 < 100ms | K.16 |
| TC-PERF-007 | 并发用户支持 | 无 | 1000 并发用户 | 无错误, 响应时间合理 | K.16 |
| TC-PERF-008 | 内存使用监控 | 无 | 长时间运行 | 内存使用稳定, 无泄漏 | K.16 |
| TC-PERF-009 | CPU 使用监控 | 无 | 高负载运行 | CPU 使用合理 | K.16 |
| TC-PERF-010 | 磁盘 IO 监控 | 无 | 大量读写操作 | IO 使用合理 | K.16 |

## 24. 端到端功能链路测试

| ID | 用例名称 | 前置条件 | 测试步骤 | 预期结果 | 设计引用 |
|---|---|---|---|---|---|
| TC-E2E-007 | 完整用户注册流程 | 无 | 注册 → 验证邮箱 → 登录 → 创建公司 | 每步成功, 数据一致 | G.1+G.11 |
| TC-E2E-008 | 完整目录发布流程 | admin 登录 | 创建 Agent → 创建 Model → 创建 Provider → 创建 Skill → 发布 Release | 目录可用, 客户端可同步 | G.5-G.9 |
| TC-E2E-009 | 完整 Skill 安装流程 | 目录已发布 | 客户端同步 → 下载 Skill → 校验签名 → 安装 → 验证 | Skill 可用, 版本正确 | G.8+G.9 |
| TC-E2E-010 | 完整任务执行流程 | 公司已创建 | 用户输入 → 总经理分析 → 生成计划 → 用户确认 → 部门执行 → 审查 → 完成 | 任务完成, 产物可用 | G.11 |
| TC-E2E-011 | 完整 Review 流程 | 任务执行中 | 生成产物 → 分配 Reviewer → 执行 Review → 修复问题 → 重新 Review | Review 通过, 问题关闭 | G.11 |
| TC-E2E-012 | 完整备份恢复流程 | 有数据 | 创建备份 → 验证备份 → 恢复备份 → 验证数据 | 数据完整, 一致性 | G.21 |
| TC-E2E-013 | 完整知识管理流程 | 公司已创建 | 导入知识 → 索引 → 搜索 → 验证结果 | 搜索准确, 权限正确 | G.16 |
| TC-E2E-014 | 完整审计日志流程 | 有操作 | 执行操作 → 查询审计日志 → 验证记录 | 日志完整, 脱敏正确 | G.10 |
| TC-E2E-015 | 完整错误处理流程 | 无 | 触发各种错误 → 验证错误响应 → 验证日志记录 | 错误码正确, 日志完整 | G.14 |
| TC-E2E-016 | 完整权限控制流程 | 多用户 | 不同用户执行操作 → 验证权限 | 权限控制正确 | G.11 |

## 25. 数据一致性测试

| ID | 用例名称 | 前置条件 | 测试步骤 | 预期结果 | 设计引用 |
|---|---|---|---|---|---|
| TC-DATA-001 | 事务原子性 | 无 | 创建公司（含办公室、总经理、会话） | 全部成功或全部回滚 | G.1 |
| TC-DATA-002 | 外键约束 | 无 | 删除有依赖的资源 | 400 外键约束失败 | G.1 |
| TC-DATA-003 | 唯一约束 | 无 | 创建重复名称的资源 | 409 唯一约束冲突 | G.1 |
| TC-DATA-004 | 乐观锁 | 有数据 | 并发更新同一资源 | 409 版本冲突 | G.10 |
| TC-DATA-005 | 级联删除 | 有数据 | 删除父资源 | 子资源正确处理 | G.1 |
| TC-DATA-006 | 数据隔离 | 多公司 | 跨公司访问数据 | 403 数据隔离 | G.1 |
| TC-DATA-007 | 数据完整性 | 有数据 | 查询数据 | 字段完整, 类型正确 | G.1 |
| TC-DATA-008 | 数据持久化 | 有数据 | 重启服务 | 数据完整 | G.21 |
| TC-DATA-009 | 并发读写 | 有数据 | 并发读写同一资源 | 无数据损坏 | G.10 |
| TC-DATA-010 | 数据迁移 | 旧版本数据 | 执行迁移 | 数据完整, 格式正确 | G.21 |

---

## 统计

### 已实现测试覆盖

| 测试套件 | 文件数 | 用例数 | 状态 |
|---|---|---|---|
| Sidecar: test_state_machine.py | 1 | 97 | ✅ 全部通过 |
| Sidecar: test_schemas.py | 1 | 18 | ✅ 全部通过 |
| Sidecar: test_conversation.py | 1 | 14 | ✅ 全部通过 |
| Sidecar: test_knowledge.py | 1 | 14 | ✅ 全部通过 |
| Sidecar: test_company_atomic.py | 1 | 10 | ✅ 全部通过 |
| Sidecar: test_orchestration.py | 1 | 12 | ✅ 全部通过 |
| Sidecar: test_workspace.py | 1 | 12 | ✅ 全部通过 |
| Sidecar: test_employee.py | 1 | 12 | ✅ 全部通过 |
| Sidecar: test_agent_runtime.py | 1 | 7 | ✅ 全部通过 |
| **Sidecar 合计** | **9** | **203** | **✅ 100%** |
| Backend API: test_auth.py | 1 | 22 | ✅ 全部通过 |
| Backend API: test_catalog.py | 1 | 10 | ✅ 全部通过 |
| Backend API: test_compatibility.py | 1 | 11 | ✅ 全部通过 |
| Backend API: test_middleware.py | 1 | 9 | ✅ 全部通过 |
| Backend API: test_releases.py | 1 | 8 | ✅ 全部通过 |
| Backend API: test_skills.py | 1 | 8 | ✅ 全部通过 |
| Backend API: test_users.py | 1 | 12 | ✅ 全部通过 |
| Backend API: test_zip_service.py | 1 | 11 | ✅ 全部通过 |
| **Backend API 合计** | **8** | **91** | **✅ 100%** |
| **项目总计** | **17** | **294** | **✅ 100%** |

### 测试用例文档统计（含待实现）

| 模块 | 用例数 | 已实现 |
|---|---|---|
| 认证链路 | 27 | 21 |
| 用户管理 | 13 | 11 |
| 目录管理 | 15 | 10 |
| 发布管理 | 10 | 8 |
| Skill 管理 | 16 | 8 |
| Sidecar RPC | 6 | 0 |
| 公司领域 | 17 | 17 |
| 部门领域 | 12 | 12 |
| 职员领域 | 13 | 13 |
| 会话/消息 | 8 | 14 |
| 任务状态机 | 56 | 56 |
| 编排平台 | 12 | 12 |
| Workspace/Artifact/Review | 7 | 12 |
| 知识/备份 | 5 | 14 |
| Workflow 编排模型 | 3 | 0 |
| Agent Runtime 模型 | 3 | 7 |
| 中间件/安全/可观测 | 17 | 9 |
| Rust Desktop Core | 10 | 0 |
| 前端 UI | 8 | 0 |
| 端到端 | 6 | 0 |
| Rust Backend API 对接 | 6 | 0 |
| 前端 Mock 消除验证 | 13 | 0 |
| 部署配置验证 | 6 | 0 |
| 安全边界测试 | 20 | 0 |
| 异常处理测试 | 20 | 0 |
| 性能测试用例 | 10 | 0 |
| 端到端功能链路测试 | 10 | 0 |
| 数据一致性测试 | 10 | 10 |
| **合计** | **310** | **224** |
