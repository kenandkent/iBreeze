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

    # P4-T1: 精简注册 — 以下模块已迁移到 Admin Backend，Sidecar 不再注册
    # from acos.rpc.methods_knowledge import KnowledgeMethods
    # knowledge_methods = KnowledgeMethods(DB_PATH)
    # knowledge_methods.register_to(server)

    # from acos.rpc.methods_backend import BackendMethods
    # backend_methods = BackendMethods(DB_PATH)
    # backend_methods.register_to(server)

    # from acos.rpc.methods_gov import GovMethods
    # gov_methods = GovMethods(DB_PATH)
    # gov_methods.register_to(server)

    # from acos.rpc.methods_approval import ApprovalMethods
    # approval_methods = ApprovalMethods(DB_PATH)
    # approval_methods.register_to(server)

    # from acos.rpc.methods_settings import SettingsMethods
    # settings_methods = SettingsMethods(DB_PATH)
    # settings_methods.register_to(server)

    from acos.rpc.methods_provider import ProviderMethods
    provider_methods = ProviderMethods(DB_PATH)
    provider_methods.register_to(server)

    from acos.rpc.methods_sys import SysMethods
    sys_methods = SysMethods(DB_PATH)
    sys_methods.register_to(server)

    from acos.rpc.methods_session import SessionMethods
    session_methods = SessionMethods(DB_PATH, require_backend=True)
    session_methods.register_to(server)

    from acos.rpc.methods_kg import KgMethods
    kg_methods = KgMethods(DB_PATH)
    kg_methods.register_to(server)

    from acos.rpc.methods_workflow import WorkflowMethods
    workflow_methods = WorkflowMethods(DB_PATH)
    workflow_methods.register_to(server)

    # from acos.rpc.methods_audit import AuditMethods
    # audit_methods = AuditMethods(DB_PATH)
    # audit_methods.register_to(server)

    log_event("methods.registered", methods=[
        # org.* (OrganizationMethods) — 27 个
        "org.company.list", "org.company.get", "org.company.create", "org.company.update",
        "org.company.delete", "org.company.restore", "org.company.activate", "org.company.dissolve",
        "org.department.list", "org.department.create", "org.department.update", "org.department.delete",
        "org.department.move", "org.department.setLeader", "org.department.freeze",
        "org.department.unfreeze", "org.department.archive", "org.department.get",
        "org.employee.list", "org.employee.create", "org.employee.update", "org.employee.delete",
        "org.employee.setManager", "org.employee.activate", "org.employee.suspend",
        "org.employee.resume", "org.employee.archive", "org.employee.transfer", "org.employee.get",
        "org.grant.create", "org.grant.list", "org.grant.get", "org.grant.revoke",
        "org.graph.get", "org.permission.resolve",
        # cap.* — 2 个（仅保留 engine.resolve / snapshot.build）
        "cap.engine.resolve", "cap.snapshot.build",
        # task.* (TaskMethods) — 6 个
        "task.create", "task.start", "task.complete",
        "task.cancel", "task.retrySubtask", "task.nodes",
        # session.* (SessionMethods) — 6 个用户侧 + 4 个内部
        "session.list", "session.get", "session.sendMessage", "session.cancel",
        "session.transcript.get", "session.resume",
        "session._suspend", "session._archive", "session._handoff", "session._reconcile",
        # provider.* (ProviderMethods) — 5 个
        "provider.list", "provider.model.list",
        "provider.runtime.start", "provider.runtime.send", "provider.runtime.cancel",
        # kg.* (KgMethods) — 4 个
        "kg.document.list", "kg.document.get", "kg.citation.get", "kg.search",
        # workflow.* (WorkflowMethods) — 4 个
        "workflow.checkpoint.list", "workflow.plan.validate",
        "workflow.task.cancel", "workflow.deadletter.resolve",
        # sys.* (SysMethods + RPCServer builtins) — 4 个
        "sys.health", "sys.shutdown", "sys.migration.status", "sys.sync.trigger",
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
