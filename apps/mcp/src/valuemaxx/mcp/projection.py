"""Project the capability registry onto MCP tools (thin projection, §3/H5).

For each capability declaring ``Surface.MCP`` this emits one :class:`MCPTool` whose
``input_schema`` is exactly the capability input model's ``model_json_schema()`` —
generated from the typed model, never hand-written — carrying the capability name
and description. A capability that does not declare MCP is never projected. The MCP
``inputSchema`` wire field maps to ``input_schema`` here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from valuemaxx.capabilities import Surface

if TYPE_CHECKING:
    from valuemaxx.capabilities import AnyCapability, Registry


@dataclass(frozen=True, slots=True)
class MCPTool:
    """One MCP tool projected from a capability (the MCP ``Tool`` wire shape).

    Attributes:
        name: the capability name (the MCP tool name).
        description: the capability description (the MCP tool description).
        input_schema: the JSON Schema for the tool arguments — exactly the
            capability input model's ``model_json_schema()`` (the MCP wire field is
            ``inputSchema``).
    """

    name: str
    description: str
    input_schema: dict[str, object]


def project_capability(cap: AnyCapability) -> MCPTool:
    """Project one capability into an :class:`MCPTool` (schema from the input model)."""
    return MCPTool(
        name=cap.name,
        description=cap.description,
        input_schema=cap.input_model.model_json_schema(),
    )


def project_tools(registry: Registry) -> tuple[MCPTool, ...]:
    """Project every ``Surface.MCP`` capability in ``registry`` into a tool."""
    return tuple(project_capability(cap) for cap in registry.for_surface(Surface.MCP))


__all__ = ["MCPTool", "project_capability", "project_tools"]
