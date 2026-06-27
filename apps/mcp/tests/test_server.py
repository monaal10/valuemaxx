"""MCP server tests — tool calls validate args, resolve tenant, and stay scoped.

The server projects the registry into tools and dispatches a call: it validates the
arguments against the capability input model, requires a tenant id, and invokes the
handler. A call missing the tenant scope is rejected; a call with bad arguments is
rejected by the input model.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError
from valuemaxx.capabilities import Registry, Surface, capability
from valuemaxx.capabilities.surfaces import Mode
from valuemaxx.mcp.server import MCPServer, UnknownToolError


class _EchoIn(BaseModel):
    tenant_id: str
    payload: str


class _EchoOut(BaseModel):
    tenant_id: str
    echoed: str


def _echo(request: _EchoIn) -> _EchoOut:
    return _EchoOut(tenant_id=request.tenant_id, echoed=request.payload)


def _server() -> MCPServer:
    registry = Registry()
    registry.register(
        capability(
            name="echo",
            input_model=_EchoIn,
            output_model=_EchoOut,
            handler=_echo,
            description="Echo the payload back within the tenant scope.",
            surfaces=Surface.MCP,
            mode=Mode.REQUEST_RESPONSE,
        )
    )
    return MCPServer(registry)


def test_list_tools_exposes_mcp_capabilities() -> None:
    """list_tools returns the projected MCP tools."""
    server = _server()
    names = {t.name for t in server.list_tools()}
    assert names == {"echo"}


def test_call_tool_validates_and_dispatches() -> None:
    """A valid call returns the handler's output as a dict."""
    server = _server()
    result = server.call_tool("echo", {"tenant_id": "tenant-a", "payload": "hi"})
    assert result == {"tenant_id": "tenant-a", "echoed": "hi"}


def test_call_tool_rejects_missing_tenant() -> None:
    """A call without a tenant id is rejected (no untenanted invocation)."""
    server = _server()
    with pytest.raises(ValidationError):
        server.call_tool("echo", {"payload": "hi"})


def test_call_tool_rejects_unknown_tool() -> None:
    """Calling a tool that is not projected is a typed error."""
    server = _server()
    with pytest.raises(UnknownToolError):
        server.call_tool("does_not_exist", {"tenant_id": "t", "payload": "x"})


def test_tool_call_is_tenant_scoped_to_its_argument() -> None:
    """The handler only ever sees the tenant supplied in the call's arguments."""
    server = _server()
    a = server.call_tool("echo", {"tenant_id": "tenant-a", "payload": "x"})
    b = server.call_tool("echo", {"tenant_id": "tenant-b", "payload": "y"})
    assert a["tenant_id"] == "tenant-a"
    assert b["tenant_id"] == "tenant-b"
