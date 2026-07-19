"""Sidecar 入口 - 启动 RPC 服务。"""

import asyncio
import json
import os
import signal
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path


def log_event(event: str, **kwargs: object) -> None:
    """输出结构化 JSON 日志。"""
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": "info",
        "event": event,
        **kwargs,
    }
    print(json.dumps(record), flush=True)


DB_PATH = "/tmp/acos.db"
MIGRATIONS_DIR = str(Path(__file__).parent.parent / "migrations")


def _is_pid_alive(pid: int) -> bool:
    """检查进程是否存活。"""
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _monitor_parent_thread(app_pid: int) -> None:
    """独立线程：定期检查主进程是否存活，死亡则杀掉整个 sidecar。"""
    log_event("sidecar.parent_monitor_started", app_pid=app_pid)
    while True:
        try:
            if not _is_pid_alive(app_pid):
                log_event("sidecar.parent_dead", app_pid=app_pid)
                # 直接杀掉整个进程组
                os.kill(os.getpid(), signal.SIGTERM)
                return
        except Exception:
            return
        import time
        time.sleep(2)


async def init_db() -> None:
    """初始化数据库：执行所有待处理的迁移。"""
    from acos.store.migrator import Migrator

    migrator = Migrator(DB_PATH)
    await migrator.run_pending_migrations(MIGRATIONS_DIR)
    log_event("db.initialized", db_path=DB_PATH)


async def run() -> None:
    """启动 sidecar 服务。"""
    from acos.rpc.server import RPCServer
    from acos.rpc.methods_org import OrganizationMethods

    log_event("sidecar.starting", version="0.1.0")

    await init_db()

    socket_path = "/tmp/acos.sock"

    # 清理旧 socket
    socket_file = Path(socket_path)
    if socket_file.exists():
        socket_file.unlink()

    server = RPCServer(socket_path=socket_path)

    org_methods = OrganizationMethods(DB_PATH)
    org_methods.register_to(server)

    from acos.rpc.methods_capability import CapabilityMethods
    cap_methods = CapabilityMethods(DB_PATH)
    cap_methods.register_to(server)

    from acos.rpc.methods_task import TaskMethods
    task_methods = TaskMethods(DB_PATH)
    task_methods.register_to(server)

    from acos.rpc.methods_knowledge import KnowledgeMethods
    knowledge_methods = KnowledgeMethods(DB_PATH)
    knowledge_methods.register_to(server)

    from acos.rpc.methods_backend import BackendMethods
    backend_methods = BackendMethods(DB_PATH)
    backend_methods.register_to(server)

    from acos.rpc.methods_provider import ProviderMethods
    provider_methods = ProviderMethods(DB_PATH)
    provider_methods.register_to(server)

    from acos.rpc.methods_gov import GovMethods
    gov_methods = GovMethods(DB_PATH)
    gov_methods.register_to(server)

    from acos.rpc.methods_approval import ApprovalMethods
    approval_methods = ApprovalMethods(DB_PATH)
    approval_methods.register_to(server)

    from acos.rpc.methods_settings import SettingsMethods
    settings_methods = SettingsMethods(DB_PATH)
    settings_methods.register_to(server)

    from acos.rpc.methods_sys import SysMethods
    sys_methods = SysMethods(DB_PATH)
    sys_methods.register_to(server)

    from acos.rpc.methods_session import SessionMethods
    session_methods = SessionMethods(DB_PATH)
    session_methods.register_to(server)

    from acos.rpc.methods_kg import KgMethods
    kg_methods = KgMethods(DB_PATH)
    kg_methods.register_to(server)

    from acos.rpc.methods_workflow import WorkflowMethods
    workflow_methods = WorkflowMethods(DB_PATH)
    workflow_methods.register_to(server)

    from acos.rpc.methods_audit import AuditMethods
    audit_methods = AuditMethods(DB_PATH)
    audit_methods.register_to(server)

    log_event("methods.registered", methods=[
        "company.list", "company.get", "company.create", "company.update", "company.delete", "company.restore",
        "department.list", "department.create", "department.update", "department.delete",
        "employee.list", "employee.create", "employee.update", "employee.delete",
        "task.list", "task.create", "task.start", "task.complete", "task.cancel",
        "knowledge.list", "knowledge.create", "knowledge.update", "knowledge.delete", "knowledge.search",
        "skill.list", "skill.get", "skill.create", "skill.update",
        "prompt.list", "prompt.get", "prompt.create", "prompt.update",
        "capability.list", "capability.get", "capability.create", "capability.update", "capability.get_bindings",
        "template.list", "template.get", "template.create", "template.update", "template.activate", "template.archive",
        "backend.list", "backend.get", "backend.create", "backend.update", "backend.setDefault",
        "backend.enable", "backend.drain", "backend.archive", "backend.probe", "backend.checkAvailability",
        "provider.list", "provider.model.list", "provider.pricingPolicy.update", "provider.budgetFreeze.clear",
        "provider.tierMapping.update", "provider.probe", "provider.credential.get", "provider.credential.set",
        "provider.credential.revoke", "provider.runtime.start", "provider.runtime.send", "provider.runtime.cancel",
        "gov.budgetPolicy.get", "gov.budgetPolicy.update", "gov.budget.get", "gov.budget.reserve",
        "gov.budget.revise", "gov.approvalType.create", "gov.approvalType.list", "gov.approvalType.get",
        "gov.approvalType.update", "gov.audit.query",
        "approval.list", "approval.get", "approval.resolve", "approval.request",
        "settings.company.get", "settings.company.update", "settings.knowledgePolicy.get",
        "settings.knowledgePolicy.update", "settings.securityPolicy.get", "settings.securityPolicy.update",
        "settings.workspacePolicy.get", "settings.workspacePolicy.update", "settings.notification.get",
        "settings.notification.update", "sys.migration.status", "cap.engine.resolve",
        "session.list", "session.get", "session.sendMessage", "session.cancel", "session.transcript.get",
        "kg.document.list", "kg.document.get", "kg.citation.get", "kg.search", "kg.source.delete",
        "kg.knowledge.reject", "kg.knowledge.confirm", "kg.ingest.retry",
        "workflow.checkpoint.list", "workflow.plan.validate", "workflow.task.cancel",
        "task.retrySubtask",
        "intervention.list", "audit.query",
    ])

    await server.start()
    log_event("rpc.listening", socket=socket_path)

    await provider_methods.ensure_manifest_imported()

    # 启动父进程监控线程
    app_pid_str = os.environ.get("IBREEZE_APP_PID")
    if app_pid_str:
        try:
            app_pid = int(app_pid_str)
            t = threading.Thread(target=_monitor_parent_thread, args=(app_pid,), daemon=True)
            t.start()
            log_event("sidecar.parent_monitor_thread", app_pid=app_pid)
        except ValueError:
            pass

    # 等待关闭信号
    stop = asyncio.Event()

    def _shutdown(*_args: object) -> None:
        log_event("sidecar.shutdown_signal")
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _shutdown)

    await stop.wait()

    await server.stop()
    log_event("sidecar.stopped")


def main() -> None:
    """CLI 入口点。"""
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
    finally:
        log_event("sidecar.exited")


if __name__ == "__main__":
    sys.exit(main() or 0)
