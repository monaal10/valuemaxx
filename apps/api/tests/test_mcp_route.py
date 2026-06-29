"""The MCP Streamable-HTTP route (POST /mcp) — a real JSON-RPC bridge to the registry.

valuemaxx ships MCP as a URL on the backend (not a pip package): the FastAPI app
exposes ``POST /mcp`` speaking MCP's JSON-RPC, bridged to the existing
:class:`~valuemaxx.mcp.MCPServer` (``list_tools`` / ``call_tool``). A user points
their MCP client (Claude Desktop/Code) at ``http://host/mcp`` after ``valuemaxx up``.

These tests drive the genuine wire: ``initialize`` -> ``tools/list`` -> ``tools/call``
over HTTP via the TestClient, asserting a real capability runs and returns its typed
output, and that an unknown ingest key is rejected (the MCP surface is tenant-scoped
like every other surface).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, cast

from fastapi.testclient import TestClient
from valuemaxx.agent_integrability.discovery import build_default_registry
from valuemaxx.api.app import build_app

if TYPE_CHECKING:
    import httpx

_API_KEYS = {"mcp-key": "tenant-mcp"}
_WEBHOOK_SECRET = b"shhh"


class _HttpClient(Protocol):
    def post(
        self,
        url: str,
        *,
        json: object | None = ...,
        headers: dict[str, str] | None = ...,
    ) -> httpx.Response: ...


def _client() -> TestClient:
    app = build_app(build_default_registry(), api_keys=_API_KEYS, webhook_secret=_WEBHOOK_SECRET)
    return TestClient(app)


def _rpc(
    client: TestClient, method: str, params: object, *, key: str = "mcp-key", rpc_id: int = 1
) -> httpx.Response:
    return cast("_HttpClient", client).post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": rpc_id, "method": method, "params": params},
        headers={"x-valuemaxx-ingest-key": key},
    )


def test_initialize_returns_protocol_and_capabilities() -> None:
    """`initialize` returns a JSON-RPC result with a protocolVersion + serverInfo."""
    resp = _rpc(_client(), "initialize", {"protocolVersion": "2025-06-18"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == 1
    result = body["result"]
    assert "protocolVersion" in result
    assert result["serverInfo"]["name"] == "valuemaxx"
    assert "tools" in result["capabilities"]


def test_tools_list_projects_every_mcp_capability() -> None:
    """`tools/list` returns the projected MCP tools with name + inputSchema (camelCase)."""
    resp = _rpc(_client(), "tools/list", {})
    assert resp.status_code == 200, resp.text
    tools = resp.json()["result"]["tools"]
    names = {t["name"] for t in tools}
    assert "list_cost_sources" in names  # a known Surface.MCP capability
    one = next(t for t in tools if t["name"] == "list_cost_sources")
    assert "inputSchema" in one  # MCP wire field is camelCase inputSchema
    assert one["description"]


def test_tools_call_runs_a_real_capability() -> None:
    """`tools/call` dispatches to the capability handler and returns its output."""
    resp = _rpc(
        _client(),
        "tools/call",
        {"name": "list_cost_sources", "arguments": {}},
    )
    assert resp.status_code == 200, resp.text
    result = resp.json()["result"]
    # MCP tool results carry a content array; the structured output is also surfaced.
    assert result["isError"] is False
    assert isinstance(result["content"], list)
    # list_cost_sources returns the wired cost-source identifiers in its output model.
    structured = result["structuredContent"]
    assert "sources" in structured
    assert isinstance(structured["sources"], list)


def test_tools_call_unknown_tool_is_a_jsonrpc_error() -> None:
    """An unknown tool name returns a JSON-RPC error, not a crash."""
    resp = _rpc(_client(), "tools/call", {"name": "no_such_tool", "arguments": {}})
    assert resp.status_code == 200, resp.text  # JSON-RPC errors ride a 200 envelope
    body = resp.json()
    assert "error" in body
    assert body["error"]["code"] == -32602  # invalid params (unknown tool)


def test_mcp_route_rejects_unknown_ingest_key() -> None:
    """The MCP surface is tenant-scoped: an unknown key is 401, not an open relay."""
    resp = _rpc(_client(), "tools/list", {}, key="not-a-real-key")
    assert resp.status_code == 401, resp.text
