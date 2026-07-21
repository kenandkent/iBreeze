"""验证 RPC 精简后的方法清单（P4-T1）。"""

import pytest
from acos.rpc.server import RPCServer


class TestRpcSlimmed:
    """验证注册精简：保留的方法可用，移除的方法不再注册。"""

    def test_capability_methods_slimmed(self) -> None:
        from acos.rpc.methods_capability import CapabilityMethods
        methods = CapabilityMethods(":memory:")
        server = RPCServer()
        methods.register_to(server)
        assert "cap.engine.resolve" in server._handlers
        assert "cap.snapshot.build" in server._handlers
        # 以下方法已从注册中移除
        removed = [
            "cap.skill.list", "cap.skill.get", "cap.skill.create", "cap.skill.update",
            "cap.prompt.list", "cap.prompt.get", "cap.prompt.create", "cap.prompt.update",
            "cap.capability.list", "cap.capability.get", "cap.capability.create",
            "cap.capability.update", "cap.metrics.get",
            "org.template.list", "org.template.get", "org.template.create",
        ]
        for m in removed:
            assert m not in server._handlers, f"{m} should have been removed"

    def test_provider_methods_slimmed(self) -> None:
        from acos.rpc.methods_provider import ProviderMethods
        methods = ProviderMethods(":memory:")
        server = RPCServer()
        methods.register_to(server)
        retained = [
            "provider.list", "provider.model.list",
            "provider.runtime.start", "provider.runtime.send", "provider.runtime.cancel",
        ]
        for m in retained:
            assert m in server._handlers, f"{m} should be retained"
        removed = [
            "provider.create", "provider.agent.list", "provider.models.fetch",
            "provider.pricingPolicy.update", "provider.budgetFreeze.clear",
            "provider.tierMapping.update", "provider.probe",
            "provider.credential.get", "provider.credential.set", "provider.credential.revoke",
        ]
        for m in removed:
            assert m not in server._handlers, f"{m} should have been removed"

    def test_kg_methods_slimmed(self) -> None:
        from acos.rpc.methods_kg import KgMethods
        methods = KgMethods(":memory:")
        server = RPCServer()
        methods.register_to(server)
        retained = [
            "kg.document.list", "kg.document.get", "kg.citation.get", "kg.search",
        ]
        for m in retained:
            assert m in server._handlers, f"{m} should be retained"
        removed = [
            "kg.source.delete", "kg.knowledge.reject",
            "kg.knowledge.confirm", "kg.ingest.retry", "kg.reindex",
        ]
        for m in removed:
            assert m not in server._handlers, f"{m} should have been removed"

    def test_sys_methods_includes_sync(self) -> None:
        from acos.rpc.methods_sys import SysMethods
        methods = SysMethods(":memory:")
        server = RPCServer()
        methods.register_to(server)
        assert "sys.migration.status" in server._handlers
        assert "sys.sync.trigger" in server._handlers
