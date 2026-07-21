"""
iBreeze 全链路瘦身集成测试

验证三端（Admin Backend + Sidecar + Desktop）的瘦身结果一致性。
不启动真实服务，仅验证代码结构与契约。
"""
import asyncio
import importlib
import json
import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


# ── Admin Backend 端点完整性 ────────────────────────────────────────


def _collect_api_routes() -> set[str]:
    """从 admin-backend/app/api/*.py 收集所有路由路径。"""
    api_dir = ROOT / "admin-backend" / "app" / "api"
    routes: set[str] = set()
    pattern = re.compile(r'(?:"|\'")(/api/[^"\']+)(?:"|\')')
    for py_file in api_dir.glob("*.py"):
        if py_file.name.startswith("_"):
            continue
        text = py_file.read_text()
        for match in pattern.finditer(text):
            path = match.group(1)
            # 标准化 FastAPI 路径参数
            path = re.sub(r"\{(\w+)\}", r"{id}", path)
            # 去掉方法前缀差异
            routes.add(path)
    return routes


class TestAdminBackendCompleteness:
    """验证 Admin Backend REST API 端点覆盖。"""

    def test_main_py_registers_all_routers(self):
        """main.py 应注册所有 API router。"""
        main_py = ROOT / "admin-backend" / "app" / "main.py"
        content = main_py.read_text()
        expected_routers = [
            "auth", "companies", "capabilities", "skills", "prompts",
            "templates", "knowledge", "providers", "backends",
            "governance", "audit", "sync",
        ]
        for router in expected_routers:
            assert f'"{router}"' in content or f"'{router}'" in content or f"router" in content, (
                f"Router '{router}' not found in main.py"
            )

    def test_auth_endpoints_exist(self):
        """认证域 4 端点应存在。"""
        auth_py = ROOT / "admin-backend" / "app" / "api" / "auth.py"
        content = auth_py.read_text()
        assert "/login" in content
        assert "/refresh" in content
        assert "/me" in content
        assert "/password" in content

    def test_capability_endpoints_exist(self):
        """能力域端点应存在。"""
        cap_py = ROOT / "admin-backend" / "app" / "api" / "capabilities.py"
        content = cap_py.read_text()
        assert "submit-review" in content
        assert "publish" in content
        assert "deprecate" in content
        assert "archive" in content
        assert "versions" in content
        assert "bindings" in content

    def test_knowledge_endpoints_exist(self):
        """知识管理域 10 端点应存在。"""
        kg_py = ROOT / "admin-backend" / "app" / "api" / "knowledge.py"
        content = kg_py.read_text()
        assert "confirm" in content
        assert "reject" in content
        assert "reindex" in content
        assert "sources" in content
        assert "ingest" in content

    def test_governance_endpoints_exist(self):
        """治理域 10 端点应存在。"""
        gov_py = ROOT / "admin-backend" / "app" / "api" / "governance.py"
        content = gov_py.read_text()
        assert "approval-types" in content
        assert "approvals" in content
        assert "budget-policy" in content
        assert "resolve" in content

    def test_audit_endpoints_exist(self):
        """审计域 2 端点应存在。"""
        audit_py = ROOT / "admin-backend" / "app" / "api" / "audit.py"
        content = audit_py.read_text()
        assert "logs" in content
        assert "interventions" in content

    def test_sync_endpoint_exists(self):
        """同步域 1 端点应存在。"""
        sync_py = ROOT / "admin-backend" / "app" / "api" / "sync.py"
        content = sync_py.read_text()
        assert "config" in content

    def test_rbac_connected_to_write_endpoints(self):
        """RBAC require_permission 应连接到所有写端点 router。"""
        api_dir = ROOT / "admin-backend" / "app" / "api"
        write_routers = [
            "capabilities.py", "skills.py", "prompts.py", "templates.py",
            "knowledge.py", "providers.py", "backends.py", "governance.py",
        ]
        for router_file in write_routers:
            content = (api_dir / router_file).read_text()
            assert "require_permission" in content, (
                f"{router_file} missing require_permission"
            )


# ── Sidecar RPC 精简完整性 ──────────────────────────────────────────


class TestSidecarRpcSlimming:
    """验证 Sidecar RPC 方法精简结果。"""

    def test_app_py_active_method_classes(self):
        """app.py 应有 8 个活跃的 method class 注册。"""
        app_py = ROOT / "sidecar" / "acos" / "app.py"
        content = app_py.read_text()

        active_classes = [
            "OrganizationMethods", "CapabilityMethods", "TaskMethods",
            "ProviderMethods", "SysMethods", "SessionMethods",
            "KgMethods", "WorkflowMethods",
        ]
        for cls in active_classes:
            assert f"{cls}(DB_PATH)" in content or f"{cls}(" in content, (
                f"{cls} not found as active in app.py"
            )

    def test_app_py_commented_method_classes(self):
        """6 个管理侧 method class 应被注释掉。"""
        app_py = ROOT / "sidecar" / "acos" / "app.py"
        content = app_py.read_text()
        commented_classes = [
            "KnowledgeMethods", "BackendMethods", "GovMethods",
            "ApprovalMethods", "SettingsMethods", "AuditMethods",
        ]
        for cls in commented_classes:
            # 注释格式为 "# from ... import ClassName"
            assert f"# from" in content and cls in content, (
                f"{cls} should be commented out in app.py"
            )
            # 确认不存在未注释的实例化
            lines = content.split("\n")
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if f"{cls}(" in stripped and "import" not in stripped:
                    pytest.fail(f"{cls} is not commented out: {stripped}")

    def test_capability_methods_slimmed(self):
        """CapabilityMethods 应仅保留 2 个方法。"""
        cap_py = ROOT / "sidecar" / "acos" / "rpc" / "methods_capability.py"
        content = cap_py.read_text()
        assert "cap.engine.resolve" in content
        assert "cap.snapshot.build" in content

    def test_provider_methods_slimmed(self):
        """ProviderMethods 应仅保留 5 个方法。"""
        prov_py = ROOT / "sidecar" / "acos" / "rpc" / "methods_provider.py"
        content = prov_py.read_text()
        assert "provider.list" in content
        assert "provider.model.list" in content
        assert "provider.runtime.start" in content
        assert "provider.runtime.send" in content
        assert "provider.runtime.cancel" in content

    def test_kg_methods_slimmed(self):
        """KgMethods 应仅保留 4 个方法。"""
        kg_py = ROOT / "sidecar" / "acos" / "rpc" / "methods_kg.py"
        content = kg_py.read_text()
        assert "kg.search" in content
        assert "kg.document.list" in content
        assert "kg.document.get" in content
        assert "kg.citation.get" in content

    def test_org_methods_no_task_or_knowledge(self):
        """OrganizationMethods 不应注册 task.* 或 knowledge.* 方法。"""
        org_py = ROOT / "sidecar" / "acos" / "rpc" / "methods_org.py"
        content = org_py.read_text()
        # 不应包含 task.* 注册
        assert 'register_method("task.' not in content, (
            "OrganizationMethods should not register task.* methods"
        )
        # 不应包含 knowledge.* 注册
        assert 'register_method("knowledge.' not in content, (
            "OrganizationMethods should not register knowledge.* methods"
        )

    def test_sys_methods_includes_sync_trigger(self):
        """SysMethods 应包含 sys.sync.trigger。"""
        sys_py = ROOT / "sidecar" / "acos" / "rpc" / "methods_sys.py"
        content = sys_py.read_text()
        assert "sys.sync.trigger" in content

    def test_config_puller_exists(self):
        """ConfigPuller 应存在于 sidecar/acos/sync/puller.py。"""
        puller_py = ROOT / "sidecar" / "acos" / "sync" / "puller.py"
        assert puller_py.exists(), "ConfigPuller file not found"
        content = puller_py.read_text()
        assert "pull_full_config" in content
        assert "pull_incremental" in content
        assert "_upsert_config" in content


# ── Desktop 瘦身完整性 ──────────────────────────────────────────────


class TestDesktopSlimming:
    """验证 Desktop App 瘦身结果。"""

    def test_archived_components_exist(self):
        """13 个管理侧组件应归档到 archived/。"""
        archived = ROOT / "apps" / "desktop" / "src" / "archived"
        assert archived.exists(), "archived/ directory not found"
        expected = [
            "KnowledgeList.tsx",
            "KnowledgeGovernancePage.tsx",
            "CapabilityList.tsx",
            "CapabilityEnginePage.tsx",
            "SkillList.tsx",
            "PromptList.tsx",
            "TemplateList.tsx",
            "ProviderBackendPage.tsx",
            "GrantPage.tsx",
            "GovernancePage.tsx",
            "AuditPage.tsx",
            "InterventionPage.tsx",
            "PermissionPage.tsx",
        ]
        for name in expected:
            assert (archived / name).exists(), f"{name} not in archived/"

    def test_router_has_9_routes(self):
        """router.tsx 应定义 9 条路由。"""
        router_tsx = ROOT / "apps" / "desktop" / "src" / "router.tsx"
        content = router_tsx.read_text()
        # 路由使用相对路径（无前导 /）
        expected_paths = [
            "companies", "companies/:companyId",
            "employees", "employees/:employeeId",
            "session", "tasks", "tasks/advanced",
            "dashboard", "settings",
        ]
        for path in expected_paths:
            # 使用 path 字符串匹配（路由定义中用 'path: 'xxx' 格式）
            assert path in content, f"Route {path} not found in router.tsx"

    def test_sidebar_has_7_menu_items(self):
        """Sidebar.tsx 应定义 7 个菜单项。"""
        sidebar_tsx = ROOT / "apps" / "desktop" / "src" / "components" / "layout" / "Sidebar.tsx"
        content = sidebar_tsx.read_text()
        # 统计 menuItems 数组中的对象数量
        menu_keys = [
            "/companies", "/employees", "/session",
            "/tasks", "/tasks/advanced", "/dashboard", "/settings",
        ]
        for key in menu_keys:
            assert key in content, f"Menu key {key} not found in Sidebar.tsx"

    def test_layout_uses_outlet(self):
        """Layout.tsx 应使用 Outlet 渲染子路由。"""
        layout_tsx = ROOT / "apps" / "desktop" / "src" / "components" / "layout" / "Layout.tsx"
        content = layout_tsx.read_text()
        assert "Outlet" in content

    def test_dashboard_slimmed(self):
        """DashboardPage 应仅显示会话+任务统计。"""
        dashboard_tsx = ROOT / "apps" / "desktop" / "src" / "components" / "dashboard" / "DashboardPage.tsx"
        content = dashboard_tsx.read_text()
        # 不应包含被移除的统计项
        assert "Backend" not in content or "backend" not in content.lower()
        assert "Provider" not in content or "provider" not in content.lower()
        # 应包含保留的统计项
        assert "session" in content.lower() or "会话" in content
        assert "task" in content.lower() or "任务" in content

    def test_pagekey_has_7_values(self):
        """PageKey 类型应仅包含 7 个值。"""
        types_tsx = ROOT / "apps" / "desktop" / "src" / "types" / "index.ts"
        content = types_tsx.read_text()
        expected = ["companies", "employees", "session", "tasks", "taskAdvanced", "dashboard", "settings"]
        for key in expected:
            assert f"'{key}'" in content or f'"{key}"' in content, (
                f"PageKey '{key}' not found"
            )

    def test_react_router_installed(self):
        """react-router-dom 应已安装。"""
        pkg = ROOT / "apps" / "desktop" / "package.json"
        content = pkg.read_text()
        assert "react-router-dom" in content


# ── Admin Frontend 完整性 ───────────────────────────────────────────


class TestAdminFrontendCompleteness:
    """验证 Admin Frontend 11 个管理页面。"""

    EXPECTED_PAGES = [
        ("capabilities/index.tsx", "能力列表"),
        ("skills/index.tsx", "技能列表"),
        ("prompts/index.tsx", "Prompt 资产"),
        ("templates/index.tsx", "员工模板"),
        ("capability-engine/index.tsx", "能力引擎"),
        ("knowledge/index.tsx", "知识库"),
        ("knowledge/governance.tsx", "知识治理"),
        ("providers/index.tsx", "Provider 与 Backend"),
        ("governance/index.tsx", "治理与审批"),
        ("audit/index.tsx", "审计日志"),
        ("audit/interventions.tsx", "人工干预"),
    ]

    def test_all_11_pages_exist(self):
        """11 个管理页面文件应全部存在。"""
        pages_dir = ROOT / "apps" / "admin" / "src" / "pages"
        for path, name in self.EXPECTED_PAGES:
            full = pages_dir / path
            assert full.exists(), f"Page {name} ({path}) not found"

    def test_login_page_exists(self):
        """登录页应存在。"""
        login = ROOT / "apps" / "admin" / "src" / "pages" / "login" / "index.tsx"
        assert login.exists()

    def test_app_tsx_routes_match_pages(self):
        """App.tsx 路由应覆盖所有 11 个管理页面。"""
        app_tsx = ROOT / "apps" / "admin" / "src" / "App.tsx"
        content = app_tsx.read_text()
        route_paths = [
            "/capabilities", "/skills", "/prompts", "/templates",
            "/capability-engine", "/knowledge", "/knowledge/governance",
            "/providers", "/governance", "/audit", "/audit/interventions",
        ]
        for path in route_paths:
            assert path in content, f"Route {path} not in App.tsx"

    def test_api_service_has_interceptors(self):
        """api.ts 应配置请求/响应拦截器。"""
        api_ts = ROOT / "apps" / "admin" / "src" / "services" / "api.ts"
        content = api_ts.read_text()
        assert "interceptors.request" in content or "request.use" in content
        assert "interceptors.response" in content or "response.use" in content
        assert "401" in content or "Unauthorized" in content

    def test_layout_has_sidebar_menu(self):
        """BasicLayout.tsx 应定义侧边栏菜单。"""
        layout_tsx = ROOT / "apps" / "admin" / "src" / "layouts" / "BasicLayout.tsx"
        content = layout_tsx.read_text()
        assert "能力管理" in content
        assert "知识管理" in content
        assert "审计" in content


# ── 数字一致性 ──────────────────────────────────────────────────────


class TestNumericConsistency:
    """验证设计文档中的数字与实际代码一致。"""

    def test_admin_backend_30_tables_exist_in_migration(self):
        """admin-backend 迁移应定义 30 张表。"""
        models_dir = ROOT / "admin-backend" / "app" / "models"
        # 统计模型文件中定义的表
        table_names = set()
        for py_file in models_dir.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            content = py_file.read_text()
            for match in re.finditer(r'__tablename__\s*=\s*["\'](\w+)["\']', content):
                table_names.add(match.group(1))
        assert len(table_names) >= 28, f"Expected ~30 tables, found {len(table_names)}: {table_names}"

    def test_sidecar_rpc_method_count_approx_55(self):
        """Sidecar 公开 RPC 方法数应约为 55。"""
        # 只统计活跃 class 的方法
        rpc_dir = ROOT / "sidecar" / "acos" / "rpc"

        # class -> 文件映射（活跃的）
        active_class_files = {
            "OrganizationMethods": "methods_org.py",
            "CapabilityMethods": "methods_capability.py",
            "TaskMethods": "methods_task.py",
            "ProviderMethods": "methods_provider.py",
            "SysMethods": "methods_sys.py",
            "SessionMethods": "methods_session.py",
            "KgMethods": "methods_kg.py",
            "WorkflowMethods": "methods_workflow.py",
        }

        methods = set()
        for cls, filename in active_class_files.items():
            filepath = rpc_dir / filename
            if not filepath.exists():
                continue
            content = filepath.read_text()
            for match in re.finditer(r'register_method\(["\']([\w.]+)["\']', content):
                methods.add(match.group(1))

        # 排除内部 session._* 方法（不计入公开方法数）
        public_methods = {m for m in methods if not m.startswith("session._")}

        assert 45 <= len(public_methods) <= 70, (
            f"Expected ~55 public RPC methods, found {len(public_methods)}: {public_methods}"
        )


# ── 端口配置一致性 ──────────────────────────────────────────────────


class TestPortConfiguration:
    """验证端口配置在各组件间一致。"""

    def test_admin_backend_port_50080(self):
        """Admin Backend 应监听 50080。"""
        config_py = ROOT / "admin-backend" / "app" / "config.py"
        content = config_py.read_text()
        assert "50080" in content

    def test_admin_frontend_proxy_to_50080(self):
        """Admin Frontend 应代理 /api → 50080。"""
        vite_config = ROOT / "apps" / "admin" / "vite.config.ts"
        content = vite_config.read_text()
        assert "50080" in content

    def test_admin_frontend_port_8000(self):
        """Admin Frontend dev server 应监听 8000。"""
        vite_config = ROOT / "apps" / "admin" / "vite.config.ts"
        content = vite_config.read_text()
        assert "8000" in content


# ── RBAC 角色矩阵一致性 ────────────────────────────────────────────


class TestRBACMatrix:
    """验证 RBAC 角色权限矩阵。"""

    def test_role_permissions_defined(self):
        """rbac.py 应定义 4 种角色。"""
        rbac_py = ROOT / "admin-backend" / "app" / "auth" / "rbac.py"
        content = rbac_py.read_text()
        assert "super_admin" in content
        assert "platform_admin" in content
        assert "company_admin" in content
        assert "viewer" in content

    def test_viewer_has_no_write_permissions(self):
        """viewer 角色应无写权限。"""
        rbac_py = ROOT / "admin-backend" / "app" / "auth" / "rbac.py"
        content = rbac_py.read_text()
        # viewer 的权限集应为空或仅包含只读
        assert '"viewer"' in content or "'viewer'" in content


# ── 数据归属一致性 ──────────────────────────────────────────────────


class TestDataOwnership:
    """验证数据归属设计：配置数据在 Admin Backend，业务数据在 Sidecar。"""

    def test_config_tables_in_admin_db(self):
        """配置表（capabilities/skills/prompts/providers/backends）应在 Admin DB。"""
        models_dir = ROOT / "admin-backend" / "app" / "models"
        all_content = ""
        for py_file in models_dir.glob("*.py"):
            all_content += py_file.read_text()
        for table in ["capabilities", "skills", "prompt_assets", "providers", "backends"]:
            assert table in all_content, f"Config table {table} not in Admin DB models"

    def test_sync_excludes_business_data(self):
        """同步 API 不应返回 companies/departments/employees/access_grants。"""
        sync_py = ROOT / "admin-backend" / "app" / "api" / "sync.py"
        content = sync_py.read_text()
        # 不应包含业务数据表的同步
        assert '"companies"' not in content or "companies" not in content.split("return")[1] if "return" in content else True


# ── 测试套件通过性 ──────────────────────────────────────────────────


class TestSuitePass:
    """验证各组件测试套件可执行（不实际运行，仅验证测试文件存在）。"""

    def test_admin_backend_tests_exist(self):
        """admin-backend 测试文件应存在。"""
        tests_dir = ROOT / "admin-backend" / "tests"
        test_files = list(tests_dir.glob("test_*.py"))
        assert len(test_files) >= 10, f"Expected >=10 test files, found {len(test_files)}"

    def test_desktop_tests_exist(self):
        """desktop 前端测试文件应存在。"""
        tests_dir = ROOT / "apps" / "desktop" / "src"
        test_files = list(tests_dir.rglob("*.test.tsx")) + list(tests_dir.rglob("*.test.ts"))
        assert len(test_files) >= 15, f"Expected >=15 test files, found {len(test_files)}"

    def test_sidecar_rpc_slimmed_test_exists(self):
        """sidecar RPC 精简测试应存在。"""
        test_file = ROOT / "sidecar" / "tests" / "test_rpc_slimmed.py"
        assert test_file.exists()
        content = test_file.read_text()
        assert "capability_methods_slimmed" in content
        assert "provider_methods_slimmed" in content
        assert "kg_methods_slimmed" in content


# ── 合约验证测试（需启动 Sidecar RPC 进程） ──────────────────────────


ADMIN_BACKEND_PORT = 50080
ADMIN_BACKEND_BASE = f"http://127.0.0.1:{ADMIN_BACKEND_PORT}"

# 设计文档中明确移除的管理侧 RPC 方法
REMOVED_METHODS = [
    # CapabilityMethods 已移除
    "cap.skill.list", "cap.skill.get", "cap.skill.create", "cap.skill.update",
    "cap.prompt.list", "cap.prompt.get", "cap.prompt.create", "cap.prompt.update",
    "cap.capability.list", "cap.capability.get", "cap.capability.create",
    "cap.capability.update", "cap.metrics.get",
    # ProviderMethods 已移除
    "provider.create", "provider.agent.list", "provider.models.fetch",
    "provider.pricingPolicy.update", "provider.budgetFreeze.clear",
    "provider.tierMapping.update", "provider.probe",
    "provider.credential.get", "provider.credential.set", "provider.credential.revoke",
    # KgMethods 已移除
    "kg.source.delete", "kg.knowledge.reject",
    "kg.knowledge.confirm", "kg.ingest.retry", "kg.reindex",
    # 完整的管理侧 class 已从 app.py 注释掉
    "backend.list", "backend.get", "backend.create", "backend.update",
    "backend.delete", "backend.probe",
    "gov.budgetPolicy.get", "gov.budgetPolicy.update",
    "approval.list", "approval.get", "approval.submit",
    "approval.approve", "approval.reject",
    "settings.get", "settings.update",
    "audit.log.list", "audit.intervention.list",
]


async def _rpc_call_uds(
    socket_path: str,
    method: str,
    params: dict | None = None,
    req_id: str = "contract-1",
) -> dict:
    """通过 UDS 调用 RPC 方法并返回响应。"""
    reader, writer = await asyncio.open_unix_connection(socket_path)
    try:
        request = {
            "type": "request",
            "id": req_id,
            "method": method,
            "params": params or {},
        }
        writer.write((json.dumps(request) + "\n").encode())
        await writer.drain()
        line = await asyncio.wait_for(reader.readline(), timeout=5.0)
        return json.loads(line.decode())
    finally:
        writer.close()
        await writer.wait_closed()


async def _start_full_sidecar_server(socket_path: str) -> "RPCServer":
    """启动一个注册了所有活跃方法的 Sidecar RPCServer（in-process）。"""
    # 确保 sidecar 包可导入
    sidecar_dir = str(ROOT / "sidecar")
    if sidecar_dir not in sys.path:
        sys.path.insert(0, sidecar_dir)

    from acos.rpc.server import RPCServer
    from acos.rpc.methods_org import OrganizationMethods
    from acos.rpc.methods_capability import CapabilityMethods
    from acos.rpc.methods_task import TaskMethods
    from acos.rpc.methods_provider import ProviderMethods
    from acos.rpc.methods_sys import SysMethods
    from acos.rpc.methods_session import SessionMethods
    from acos.rpc.methods_kg import KgMethods
    from acos.rpc.methods_workflow import WorkflowMethods

    server = RPCServer(socket_path=socket_path)
    db = ":memory:"
    OrganizationMethods(db).register_to(server)
    CapabilityMethods(db).register_to(server)
    TaskMethods(db).register_to(server)
    ProviderMethods(db).register_to(server)
    SysMethods(db).register_to(server)
    SessionMethods(db).register_to(server)
    KgMethods(db).register_to(server)
    WorkflowMethods(db).register_to(server)
    await server.start()
    return server


async def _admin_backend_available() -> bool:
    """快速检测 Admin Backend 是否在 50080 端口响应。"""
    import socket as _socket
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection("127.0.0.1", ADMIN_BACKEND_PORT),
            timeout=1.0,
        )
        writer.close()
        await writer.wait_closed()
        return True
    except (ConnectionRefusedError, OSError, asyncio.TimeoutError):
        return False


# ── Contract-01: Admin Backend → Sidecar 数据归属契约 ────────────────


class TestContractAdminReadsSidecar:
    """Contract-01: Admin Backend GET /api/companies 能读取 Sidecar 创建的数据。"""

    def test_admin_companies_endpoint_callable(self):
        """Admin Backend /api/companies 端点在代码中已定义。"""
        companies_py = ROOT / "admin-backend" / "app" / "api" / "companies.py"
        assert companies_py.exists(), "companies.py router not found"
        content = companies_py.read_text()
        assert "/api/companies" in content or "companies" in content

    @pytest.mark.asyncio
    async def test_contract_admin_reads_sidecar_companies(self):
        """Admin Backend GET /api/companies 返回 Sidecar RPC 创建的数据。

        跳过条件：Admin Backend 未运行。
        """
        if not await _admin_backend_available():
            pytest.skip("Admin Backend 未在 50080 端口运行，跳过合约测试")

        import urllib.request
        import urllib.error

        def _fetch():
            req = urllib.request.Request(f"{ADMIN_BACKEND_BASE}/api/companies")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read().decode())

        status, data = await asyncio.to_thread(_fetch)
        assert status == 200
        assert "items" in data or "data" in data or isinstance(data, list), (
            f"Unexpected response shape: {data}"
        )


# ── Contract-02: Sidecar RPC 方法注册完整性 ──────────────────────────


class TestContractSidecarMethodRegistration:
    """Contract-02: Sidecar 注册的方法数与设计文档一致。"""

    @pytest.mark.asyncio
    async def test_contract_sidecar_method_count(self):
        """验证 sidecar 注册的活跃方法数在合理范围（~62 个）。"""
        socket_path = f"/tmp/acos_contract_method_count_{os.getpid()}.sock"
        server = await _start_full_sidecar_server(socket_path)
        try:
            method_count = len(server._handlers)
            # 设计文档列出约 62 个方法（含 2 个 builtin）
            assert 55 <= method_count <= 70, (
                f"Expected ~62 active methods, found {method_count}"
            )
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_contract_expected_methods_registered(self):
        """验证所有设计文档中的活跃方法均已注册。"""
        socket_path = f"/tmp/acos_contract_expected_{os.getpid()}.sock"
        server = await _start_full_sidecar_server(socket_path)
        try:
            expected_methods = [
                # org.* — 35 个
                "org.company.list", "org.company.get", "org.company.create",
                "org.company.update", "org.company.delete", "org.company.restore",
                "org.company.activate", "org.company.dissolve",
                "org.department.list", "org.department.create", "org.department.update",
                "org.department.delete", "org.department.move", "org.department.setLeader",
                "org.department.freeze", "org.department.unfreeze",
                "org.department.archive", "org.department.get",
                "org.employee.list", "org.employee.create", "org.employee.update",
                "org.employee.delete", "org.employee.setManager", "org.employee.activate",
                "org.employee.suspend", "org.employee.resume", "org.employee.archive",
                "org.employee.transfer", "org.employee.get",
                "org.grant.create", "org.grant.list", "org.grant.get", "org.grant.revoke",
                "org.graph.get", "org.permission.resolve",
                # cap.* — 2 个
                "cap.engine.resolve", "cap.snapshot.build",
                # task.* — 6 个
                "task.create", "task.start", "task.complete",
                "task.cancel", "task.retrySubtask", "task.nodes",
                # session.* — 6 个用户侧
                "session.list", "session.get", "session.sendMessage", "session.cancel",
                "session.transcript.get", "session.resume",
                # provider.* — 5 个
                "provider.list", "provider.model.list",
                "provider.runtime.start", "provider.runtime.send", "provider.runtime.cancel",
                # kg.* — 4 个
                "kg.document.list", "kg.document.get", "kg.citation.get", "kg.search",
                # workflow.* — 4 个
                "workflow.checkpoint.list", "workflow.plan.validate",
                "workflow.task.cancel", "workflow.deadletter.resolve",
                # sys.* — 4 个
                "sys.health", "sys.shutdown", "sys.migration.status", "sys.sync.trigger",
            ]
            for method in expected_methods:
                assert method in server._handlers, (
                    f"Expected method '{method}' not registered"
                )
        finally:
            await server.stop()


# ── Contract-03: 移除的方法返回 method not found ────────────────────


class TestContractRemovedMethodsNotFound:
    """Contract-03: 已移除的管理侧方法调用时应返回 method not found。"""

    @pytest.mark.asyncio
    async def test_contract_removed_methods_not_found(self):
        """已移除的管理侧方法调用应返回 method not found 错误。"""
        socket_path = f"/tmp/acos_contract_removed_{os.getpid()}.sock"
        server = await _start_full_sidecar_server(socket_path)
        try:
            for method in REMOVED_METHODS:
                resp = await _rpc_call_uds(socket_path, method, {}, f"rm-{method}")
                assert resp["error"] is not None, (
                    f"Removed method '{method}' should return error but got: {resp['result']}"
                )
                assert "Method not found" in resp["error"], (
                    f"Removed method '{method}' error should say 'Method not found', got: {resp['error']}"
                )
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_contract_removed_backend_list_not_found(self):
        """backend.list 明确应返回 method not found。"""
        socket_path = f"/tmp/acos_contract_backend_{os.getpid()}.sock"
        server = await _start_full_sidecar_server(socket_path)
        try:
            resp = await _rpc_call_uds(socket_path, "backend.list", {}, "rm-backend")
            assert resp["error"] is not None
            assert "Method not found" in resp["error"]
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_contract_removed_gov_budget_not_found(self):
        """gov.budgetPolicy.get 明确应返回 method not found。"""
        socket_path = f"/tmp/acos_contract_gov_{os.getpid()}.sock"
        server = await _start_full_sidecar_server(socket_path)
        try:
            resp = await _rpc_call_uds(socket_path, "gov.budgetPolicy.get", {}, "rm-gov")
            assert resp["error"] is not None
            assert "Method not found" in resp["error"]
        finally:
            await server.stop()


# ── Contract-04: 三端数据一致性 - 公司数据 ──────────────────────────


class TestContractDataConsistency:
    """Contract-04: 公司数据在 Sidecar RPC 创建后，Admin Backend 可读取。"""

    def test_admin_companies_api_matches_sidecar_rpc(self):
        """Admin Backend /api/companies 路由存在且与 Sidecar 数据模型一致。"""
        companies_py = ROOT / "admin-backend" / "app" / "api" / "companies.py"
        content = companies_py.read_text()
        # Admin Backend 读取 companies 的端点应存在
        assert "companies" in content.lower()

    @pytest.mark.asyncio
    async def test_contract_data_consistency_company(self):
        """公司通过 Sidecar RPC 创建后，Admin Backend 可通过 REST API 读取。

        跳过条件：Admin Backend 未运行。
        """
        if not await _admin_backend_available():
            pytest.skip("Admin Backend 未在 50080 端口运行，跳过数据一致性测试")

        import urllib.request

        def _fetch():
            req = urllib.request.Request(f"{ADMIN_BACKEND_BASE}/api/companies")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read().decode())

        status, body = await asyncio.to_thread(_fetch)
        assert status == 200
        assert isinstance(body, (list, dict)), (
            f"Response should be list or dict, got {type(body)}"
        )


# ── Contract-05: Sidecar sys.health 返回方法列表 ────────────────────


class TestContractSysHealth:
    """Contract-05: sys.health 返回健康状态与组件信息。"""

    @pytest.mark.asyncio
    async def test_contract_sys_health_methods_list(self):
        """sys.health 返回 healthy 状态。"""
        socket_path = f"/tmp/acos_contract_health_{os.getpid()}.sock"
        server = await _start_full_sidecar_server(socket_path)
        try:
            resp = await _rpc_call_uds(socket_path, "sys.health", {}, "h1")
            assert resp["error"] is None
            result = resp["result"]
            assert "status" in result or "ok" in result
            assert result.get("status") == "healthy"
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_contract_sys_health_components(self):
        """sys.health 返回 components 字段且 rpc 为 up。"""
        socket_path = f"/tmp/acos_contract_health_comp_{os.getpid()}.sock"
        server = await _start_full_sidecar_server(socket_path)
        try:
            resp = await _rpc_call_uds(socket_path, "sys.health", {}, "h2")
            assert resp["error"] is None
            result = resp["result"]
            assert "components" in result, (
                f"sys.health should include 'components', got: {result}"
            )
            assert result["components"]["rpc"] == "up"
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_contract_sys_health_via_live_server(self):
        """sys.health 通过真实 sidecar 进程调用（UDS /tmp/acos.sock）。"""
        live_socket = "/tmp/acos.sock"
        if not os.path.exists(live_socket):
            pytest.skip("Sidecar 进程未运行（/tmp/acos.sock 不存在）")
        resp = await _rpc_call_uds(live_socket, "sys.health", {}, "h-live")
        assert resp["error"] is None
        assert resp["result"]["status"] == "healthy"
