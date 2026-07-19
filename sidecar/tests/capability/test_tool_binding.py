"""tool_binding 单元测试。"""

import pytest
from acos.capability.tool_binding import ToolBindingValidator, ToolCallResult


@pytest.fixture
def validator() -> ToolBindingValidator:
    return ToolBindingValidator()


class MockEmployee:
    def __init__(self, status: str = "active", allowed_tools: list[str] | None = None):
        self.status = status
        self.allowed_tools = allowed_tools


class MockWorkspace:
    def __init__(self, allowed_tools: list[str] | None = None):
        self.allowed_tools = allowed_tools


class TestToolBindingValidator:
    async def test_full_chain_pass(self, validator: ToolBindingValidator) -> None:
        employee = MockEmployee()
        workspace = MockWorkspace()
        snapshot = {"allowed_tools": ["search", "code"]}
        tool_call = {"tool_name": "search", "input": "query"}

        result = await validator.validate_tool_call(employee, workspace, snapshot, tool_call)
        assert result.allowed is True
        assert result.matched_rule == "runtime_policy"
        assert result.tool_call_hash != ""

    async def test_acl_no_employee(self, validator: ToolBindingValidator) -> None:
        result = await validator.validate_tool_call(None, None, {}, {"tool_name": "x"})
        assert result.allowed is False
        assert result.error_code == "AUTH-NO-EMPLOYEE"

    async def test_acl_inactive_employee(self, validator: ToolBindingValidator) -> None:
        employee = MockEmployee(status="archived")
        result = await validator.validate_tool_call(employee, None, {}, {"tool_name": "x"})
        assert result.allowed is False
        assert result.error_code == "AUTH-EMPLOYEE-INACTIVE"

    async def test_acl_tool_denied(self, validator: ToolBindingValidator) -> None:
        employee = MockEmployee(allowed_tools=["search"])
        result = await validator.validate_tool_call(employee, None, {}, {"tool_name": "code"})
        assert result.allowed is False
        assert result.error_code == "AUTH-TOOL-DENIED"

    async def test_acl_tool_allowed(self, validator: ToolBindingValidator) -> None:
        employee = MockEmployee(allowed_tools=["search", "code"])
        result = await validator.validate_tool_call(
            employee, None, {"allowed_tools": ["search"]}, {"tool_name": "search"}
        )
        assert result.allowed is True

    async def test_workspace_no_restrictions(self, validator: ToolBindingValidator) -> None:
        employee = MockEmployee()
        workspace = MockWorkspace()
        result = await validator.validate_tool_call(employee, workspace, {"allowed_tools": ["x"]}, {"tool_name": "x"})
        assert result.allowed is True

    async def test_workspace_tool_not_in_whitelist(self, validator: ToolBindingValidator) -> None:
        employee = MockEmployee()
        workspace = MockWorkspace(allowed_tools=["search"])
        result = await validator.validate_tool_call(employee, workspace, {"allowed_tools": ["code"]}, {"tool_name": "code"})
        assert result.allowed is False
        assert result.error_code == "WS-TOOL-NOT-IN-WHITELIST"

    async def test_workspace_tool_in_whitelist(self, validator: ToolBindingValidator) -> None:
        employee = MockEmployee()
        workspace = MockWorkspace(allowed_tools=["search", "code"])
        result = await validator.validate_tool_call(employee, workspace, {"allowed_tools": ["search"]}, {"tool_name": "search"})
        assert result.allowed is True

    async def test_capability_tool_not_allowed(self, validator: ToolBindingValidator) -> None:
        employee = MockEmployee()
        snapshot = {"allowed_tools": ["search"]}
        result = await validator.validate_tool_call(employee, None, snapshot, {"tool_name": "code"})
        assert result.allowed is False
        assert result.error_code == "CAP-TOOL-NOT-ALLOWED"

    async def test_capability_tool_allowed(self, validator: ToolBindingValidator) -> None:
        employee = MockEmployee()
        snapshot = {"allowed_tools": ["search", "code"]}
        result = await validator.validate_tool_call(employee, None, snapshot, {"tool_name": "search"})
        assert result.allowed is True

    async def test_runtime_policy_hash(self, validator: ToolBindingValidator) -> None:
        employee = MockEmployee()
        tool_call = {"tool_name": "search", "input": "test"}
        result = await validator.validate_tool_call(employee, None, {"allowed_tools": ["search"]}, tool_call)
        assert result.tool_call_hash != ""
        assert len(result.tool_call_hash) == 64

    async def test_runtime_policy_requires_approval(self, validator: ToolBindingValidator) -> None:
        employee = MockEmployee()
        tool_call = {"tool_name": "search", "requires_approval": True}
        result = await validator.validate_tool_call(employee, None, {"allowed_tools": ["search"]}, tool_call)
        assert result.requires_approval is True

    async def test_runtime_policy_no_approval(self, validator: ToolBindingValidator) -> None:
        employee = MockEmployee()
        tool_call = {"tool_name": "search"}
        result = await validator.validate_tool_call(employee, None, {"allowed_tools": ["search"]}, tool_call)
        assert result.requires_approval is False

    async def test_short_circuit_acl(self, validator: ToolBindingValidator) -> None:
        result = await validator.validate_tool_call(None, None, {"allowed_tools": ["x"]}, {"tool_name": "x"})
        assert result.allowed is False
        assert result.error_code == "AUTH-NO-EMPLOYEE"

    async def test_tool_call_result_defaults(self) -> None:
        r = ToolCallResult(allowed=True)
        assert r.allowed is True
        assert r.error_code == ""
        assert r.tool_call_hash == ""
        assert r.matched_rule == ""
        assert r.requires_approval is False
