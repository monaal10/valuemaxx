"""valuemaxx.mcp — MCP server projection of the capability registry.

Each capability declaring ``Surface.MCP`` is projected to one MCP tool whose
``inputSchema`` is the capability input model's ``model_json_schema()`` (generated,
never hand-written). The server validates a tool call against that input model
(rejecting an untenanted or malformed call), invokes the capability handler, and
returns the typed output. Use :func:`build_default_server` to project the canonical
registry (every logic package's capabilities).
"""

from __future__ import annotations

from valuemaxx.agent_integrability.discovery import build_default_registry
from valuemaxx.mcp.projection import MCPTool, project_capability, project_tools
from valuemaxx.mcp.server import MCPServer, UnknownToolError


def build_default_server() -> MCPServer:
    """Build an :class:`MCPServer` over the canonical capability registry."""
    return MCPServer(build_default_registry())


__all__ = [
    "MCPServer",
    "MCPTool",
    "UnknownToolError",
    "build_default_server",
    "project_capability",
    "project_tools",
]
