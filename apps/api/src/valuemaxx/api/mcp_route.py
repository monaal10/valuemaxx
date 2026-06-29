"""The MCP transport — a Streamable-HTTP JSON-RPC route over the capability registry.

valuemaxx ships MCP as a **URL on the backend**, not a separate package: ``valuemaxx up``
serves ``POST /mcp`` speaking MCP's JSON-RPC 2.0, so a user points their MCP client
(Claude Desktop/Code) at ``http://host/mcp``. This module is the thin TRANSPORT — it
decodes the JSON-RPC envelope and bridges the three MCP methods onto the existing
:class:`~valuemaxx.mcp.MCPServer` (``list_tools`` / ``call_tool``), which is itself a
projection of the capability registry. No tool is hand-written here; a capability is on
the MCP surface iff it declares ``Surface.MCP``.

Transport scope: a single ``POST /mcp`` that returns a JSON response per request
(Streamable HTTP without the optional SSE upgrade — sufficient for the request/response
tool calls valuemaxx exposes). The tenant is resolved from the ingest key on every call
(``x-valuemaxx-ingest-key``, or ``X-API-Key``), exactly like every other surface, and a
bad key is a 401 — the MCP surface is never an open relay.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from fastapi import Header, HTTPException, Request
from pydantic import ValidationError
from valuemaxx.api.errors import AuthError
from valuemaxx.mcp import MCPServer, UnknownToolError

if TYPE_CHECKING:
    from fastapi import FastAPI
    from valuemaxx.api.auth import ApiKeyAuthenticator
    from valuemaxx.capabilities import Registry

# JSON-RPC 2.0 error codes (subset we emit).
_PARSE_ERROR = -32700
_INVALID_REQUEST = -32600
_METHOD_NOT_FOUND = -32601
_INVALID_PARAMS = -32602

# The MCP protocol version this transport implements (date-based, per the MCP spec).
_PROTOCOL_VERSION = "2025-06-18"
_SERVER_INFO = {"name": "valuemaxx", "version": "0.0.0"}


def _result(rpc_id: object, result: dict[str, object]) -> dict[str, object]:
    return {"jsonrpc": "2.0", "id": rpc_id, "result": result}


def _error(rpc_id: object, code: int, message: str) -> dict[str, object]:
    return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": code, "message": message}}


def _tool_wire(name: str, description: str, input_schema: dict[str, object]) -> dict[str, object]:
    """One MCP ``Tool`` in wire shape (the ``input_schema`` field is ``inputSchema``)."""
    return {"name": name, "description": description, "inputSchema": input_schema}


def _as_dict(value: object) -> dict[str, object]:
    return cast("dict[str, object]", value) if isinstance(value, dict) else {}


def mount_mcp_route(app: FastAPI, registry: Registry, auth: ApiKeyAuthenticator) -> None:
    """Mount ``POST /mcp`` — the MCP JSON-RPC transport for SDK/agent clients.

    The :class:`MCPServer` is built once over the registry (the projected tools are
    stable for the app's lifetime). Each request resolves its tenant from the ingest
    key, decodes the JSON-RPC envelope, and dispatches ``initialize`` / ``tools/list`` /
    ``tools/call`` (plus the ``notifications/initialized`` no-op). Unknown methods and
    bad tool arguments become JSON-RPC errors on a 200 envelope (the JSON-RPC contract);
    an unknown ingest key is an HTTP 401 (auth precedes the protocol).
    """
    server = MCPServer(registry)

    async def handle(
        request: Request,
        x_valuemaxx_ingest_key: str | None = Header(default=None),
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, object]:
        # Auth first: the MCP surface is tenant-scoped like every other surface. (The
        # resolved tenant is not yet threaded into tool arguments — tenant-scoped tools
        # still require an explicit tenant_id argument, validated by their input model —
        # but an unknown key never reaches the protocol.)
        try:
            auth.resolve_tenant(x_valuemaxx_ingest_key or x_api_key)
        except AuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

        try:
            envelope = _as_dict(await request.json())
        except (ValueError, TypeError):
            return _error(None, _PARSE_ERROR, "invalid JSON")

        rpc_id = envelope.get("id")
        method = envelope.get("method")
        params = _as_dict(envelope.get("params"))

        if not isinstance(method, str):
            return _error(rpc_id, _INVALID_REQUEST, "missing or non-string 'method'")

        if method == "initialize":
            return _result(
                rpc_id,
                {
                    "protocolVersion": _PROTOCOL_VERSION,
                    "serverInfo": _SERVER_INFO,
                    "capabilities": {"tools": {"listChanged": False}},
                },
            )

        if method in ("notifications/initialized", "initialized"):
            # A notification has no id and expects no result; ack with an empty result.
            return _result(rpc_id, {})

        if method == "tools/list":
            tools = [_tool_wire(t.name, t.description, t.input_schema) for t in server.list_tools()]
            return _result(rpc_id, {"tools": tools})

        if method == "tools/call":
            name = params.get("name")
            if not isinstance(name, str):
                return _error(rpc_id, _INVALID_PARAMS, "tools/call requires a string 'name'")
            arguments = _as_dict(params.get("arguments"))
            try:
                output = server.call_tool(name, arguments)
            except UnknownToolError:
                return _error(rpc_id, _INVALID_PARAMS, f"unknown tool {name!r}")
            except ValidationError as exc:
                # Bad arguments are a tool error, surfaced in the MCP result (isError), not
                # a transport failure — the client sees the validation detail.
                return _result(
                    rpc_id,
                    {
                        "isError": True,
                        "content": [{"type": "text", "text": f"invalid arguments: {exc}"}],
                    },
                )
            # MCP tool result: a human-readable content block + the structured output.
            return _result(
                rpc_id,
                {
                    "isError": False,
                    "content": [{"type": "text", "text": _summarize(output)}],
                    "structuredContent": output,
                },
            )

        return _error(rpc_id, _METHOD_NOT_FOUND, f"unknown method {method!r}")

    app.post("/mcp", name="mcp")(handle)


def _summarize(output: dict[str, object]) -> str:
    """A compact text rendering of a tool's structured output for the content block."""
    import json

    try:
        return json.dumps(output, default=str)
    except (TypeError, ValueError):  # pragma: no cover - structured output is JSON by contract
        return str(output)


__all__ = ["mount_mcp_route"]
