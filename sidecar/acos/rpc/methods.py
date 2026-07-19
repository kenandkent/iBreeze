"""Echo RPC 方法集合。"""

from __future__ import annotations

from typing import Any

from acos.rpc.server import RPCServer


class EchoMethods:
    """一组 echo 类型的 RPC 方法，用于类型回显和连通性测试。"""

    def register_to(self, server: RPCServer) -> None:
        """将所有 echo 方法注册到给定的 RPCServer。"""
        server.register_method("echo.string", self._echo_string)
        server.register_method("echo.int", self._echo_int)
        server.register_method("echo.float", self._echo_float)
        server.register_method("echo.bool", self._echo_bool)
        server.register_method("echo.array", self._echo_array)
        server.register_method("echo.object", self._echo_object)
        server.register_method("echo.null", self._echo_null)
        server.register_method("echo.mirror", self._echo_mirror)

    async def _echo_string(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"value": params.get("value", "")}

    async def _echo_int(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"value": params.get("value", 0)}

    async def _echo_float(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"value": params.get("value", 0.0)}

    async def _echo_bool(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"value": params.get("value", False)}

    async def _echo_array(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"value": params.get("value", [])}

    async def _echo_object(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"value": params.get("value", {})}

    async def _echo_null(self, _params: dict[str, Any]) -> dict[str, Any]:
        return {"value": None}

    async def _echo_mirror(self, _params: dict[str, Any]) -> dict[str, Any]:
        return {"echo": True}
