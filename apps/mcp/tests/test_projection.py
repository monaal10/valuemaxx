"""MCP projection tests — every MCP capability becomes a tool with the right schema.

The MCP surface is a thin projection of the capability registry: for each
capability declaring ``Surface.MCP`` it emits one tool whose ``inputSchema`` is
exactly the capability input model's ``model_json_schema()`` (generated, never
hand-written), with the capability name and description. A capability that does NOT
declare MCP is never projected.
"""

from __future__ import annotations

from pydantic import BaseModel
from valuemaxx.agent_integrability.discovery import build_default_registry
from valuemaxx.capabilities import Registry, Surface, capability
from valuemaxx.capabilities.surfaces import Mode
from valuemaxx.mcp import build_default_server
from valuemaxx.mcp.projection import MCPTool, project_tools


class _ToolIn(BaseModel):
    tenant_id: str
    value: int


class _ToolOut(BaseModel):
    ok: bool


def _handler(_request: _ToolIn) -> _ToolOut:
    return _ToolOut(ok=True)


def _registry_with(*, surfaces: Surface) -> Registry:
    registry = Registry()
    registry.register(
        capability(
            name="probe_tool",
            input_model=_ToolIn,
            output_model=_ToolOut,
            handler=_handler,
            description="A probe capability for projection tests.",
            surfaces=surfaces,
            mode=Mode.REQUEST_RESPONSE,
        )
    )
    return registry


def test_input_schema_equals_model_json_schema() -> None:
    """The tool inputSchema deep-equals the capability input model's json schema."""
    registry = _registry_with(surfaces=Surface.MCP)
    tools = project_tools(registry)
    assert len(tools) == 1
    tool = tools[0]
    assert isinstance(tool, MCPTool)
    assert tool.name == "probe_tool"
    assert tool.description == "A probe capability for projection tests."
    assert tool.input_schema == _ToolIn.model_json_schema()


def test_non_mcp_capability_is_not_projected() -> None:
    """A capability that does not declare MCP yields no tool."""
    registry = _registry_with(surfaces=Surface.API | Surface.CLI)
    assert project_tools(registry) == ()


def test_every_mcp_capability_becomes_a_tool() -> None:
    """Over the real registry, each MCP capability maps to exactly one tool."""
    registry = build_default_registry()
    tools = project_tools(registry)
    tool_names = {t.name for t in tools}
    expected = {c.name for c in registry.for_surface(Surface.MCP)}
    assert tool_names == expected


def test_real_tool_schemas_match_capability_input_models() -> None:
    """Every projected tool's schema equals its capability input model's json schema."""
    registry = build_default_registry()
    by_name = {c.name: c for c in registry.all()}
    for tool in project_tools(registry):
        cap = by_name[tool.name]
        assert tool.input_schema == cap.input_model.model_json_schema()


def test_build_default_server_projects_canonical_mcp_tools() -> None:
    """build_default_server exposes exactly the canonical registry's MCP tools."""
    server = build_default_server()
    registry = build_default_registry()
    server_names = {t.name for t in server.list_tools()}
    expected = {c.name for c in registry.for_surface(Surface.MCP)}
    assert server_names == expected
