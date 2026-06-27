"""The MCP server — a thin dispatcher over the projected tools.

The server holds the projected MCP tools and dispatches a tool call: it validates
the raw arguments against the capability's input model (so an untenanted or
malformed call is rejected at the boundary), invokes the handler, and returns the
output model as a plain dict. The server never hand-codes a tool — it projects them
all from the registry, so a capability is on the MCP surface iff it declares it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from valuemaxx.capabilities import CapabilityError, Surface
from valuemaxx.mcp.projection import project_tools

if TYPE_CHECKING:
    from valuemaxx.capabilities import AnyCapability, Registry
    from valuemaxx.mcp.projection import MCPTool


class UnknownToolError(CapabilityError):
    """A tool call named a tool that is not projected onto the MCP surface."""


class MCPServer:
    """Dispatches MCP tool calls against the registry's MCP-declaring capabilities."""

    def __init__(self, registry: Registry) -> None:
        self._tools: tuple[MCPTool, ...] = project_tools(registry)
        self._by_name: dict[str, AnyCapability] = {
            cap.name: cap for cap in registry.for_surface(Surface.MCP)
        }

    def list_tools(self) -> tuple[MCPTool, ...]:
        """The projected MCP tools (name, description, generated inputSchema)."""
        return self._tools

    def call_tool(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        """Validate ``arguments`` against the tool's input model, dispatch, return the output.

        Raises :class:`UnknownToolError` if ``name`` is not an MCP tool, and a
        pydantic ``ValidationError`` if the arguments do not satisfy the capability
        input model (e.g. a missing tenant id).
        """
        cap = self._by_name.get(name)
        if cap is None:
            raise UnknownToolError(f"no MCP tool named {name!r}")
        request = cap.input_model.model_validate(arguments)
        response = cap.handler(request)
        return response.model_dump(mode="json")


__all__ = ["MCPServer", "UnknownToolError"]
