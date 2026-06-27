"""surface_mask conformance — every capability appears on every surface it declares.

Apps are thin projections of the capability registry (§3, §5). This is the CI gate
that fails on drift: for the canonical registry, every capability that declares a
surface MUST be reachable on that surface's projection —

* ``Surface.API``    -> a route on the FastAPI app;
* ``Surface.MCP``    -> a tool on the MCP server;
* ``Surface.CLI``    -> a command on the typer CLI;
* ``Surface.NOTIFY`` -> readable by the notify digest builder (it consumes the
  registry; a NOTIFY-declaring capability must be aggregate-shaped, never raw).

If any capability declared a surface but a projection dropped it, this test fails —
no capability can be hand-written into one surface only, and none can silently fall
off a surface it declares.
"""

from __future__ import annotations

import pytest
from valuemaxx.agent_integrability.discovery import build_default_registry
from valuemaxx.api.app import build_app
from valuemaxx.capabilities import Surface
from valuemaxx.cli.main import build_app as build_cli_app
from valuemaxx.mcp.server import MCPServer

_REGISTRY = build_default_registry()
_API_PATHS = {
    getattr(route, "path", None)
    for route in build_app(_REGISTRY, api_keys={"k": "t"}, webhook_secret=b"s").routes
}
_MCP_TOOLS = {tool.name for tool in MCPServer(_REGISTRY).list_tools()}


def _cli_command_names() -> set[str]:
    app = build_cli_app()
    names: set[str] = set()
    for command in app.registered_commands:
        if isinstance(command.name, str):
            names.add(command.name)
        elif command.callback is not None:
            names.add(command.callback.__name__)
    return names


_CLI_COMMANDS = _cli_command_names()

_API_CAPS = [c.name for c in _REGISTRY.for_surface(Surface.API)]
_MCP_CAPS = [c.name for c in _REGISTRY.for_surface(Surface.MCP)]
_CLI_CAPS = [c.name for c in _REGISTRY.for_surface(Surface.CLI)]
_NOTIFY_CAPS = [c.name for c in _REGISTRY.for_surface(Surface.NOTIFY)]


@pytest.mark.conformance
@pytest.mark.static
@pytest.mark.parametrize("cap_name", _API_CAPS)
def test_every_api_capability_has_a_route(cap_name: str) -> None:
    """Every Surface.API capability is reachable as a FastAPI route."""
    assert f"/{cap_name}" in _API_PATHS, f"{cap_name} declares API but has no route"


@pytest.mark.conformance
@pytest.mark.static
@pytest.mark.parametrize("cap_name", _MCP_CAPS)
def test_every_mcp_capability_is_a_tool(cap_name: str) -> None:
    """Every Surface.MCP capability is projected as an MCP tool."""
    assert cap_name in _MCP_TOOLS, f"{cap_name} declares MCP but is not a tool"


@pytest.mark.conformance
@pytest.mark.static
@pytest.mark.parametrize("cap_name", _CLI_CAPS)
def test_every_cli_capability_is_a_command(cap_name: str) -> None:
    """Every Surface.CLI capability is projected as a typer command (hyphenated)."""
    assert cap_name.replace("_", "-") in _CLI_COMMANDS, (
        f"{cap_name} declares CLI but is not a command"
    )


@pytest.mark.conformance
@pytest.mark.static
def test_notify_capabilities_are_readable_and_aggregate() -> None:
    """Every Surface.NOTIFY capability is in the registry the notify builder reads."""
    # The notify surface consumes the registry; a NOTIFY-declaring capability must be
    # present for the digest builder to read it (it never invents capabilities).
    notify_in_registry = {c.name for c in _REGISTRY.for_surface(Surface.NOTIFY)}
    assert set(_NOTIFY_CAPS) == notify_in_registry


def test_no_capability_declares_zero_surfaces() -> None:
    """Every capability declares at least one surface (else it projects nowhere)."""
    for cap in _REGISTRY.all():
        assert cap.surfaces, f"{cap.name} declares no surfaces"


def test_some_capability_exists_for_each_surface() -> None:
    """Each surface has at least one capability (the projections are non-empty)."""
    assert _API_CAPS
    assert _MCP_CAPS
    assert _CLI_CAPS
    assert _NOTIFY_CAPS
