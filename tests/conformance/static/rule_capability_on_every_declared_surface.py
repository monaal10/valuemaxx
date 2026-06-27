"""capability_on_every_declared_surface — a capability must appear on every surface it declares.

Apps are thin projections of the capability registry (§3, §5): a capability is never
hand-written into one surface only, and none may silently fall off a surface it
declares. This rule computes the cross-surface DRIFT report — for the canonical
registry, every (capability, declared surface) pair that is NOT reachable on that
surface's projection. The foundation report is empty (no drift); the negative fixture
is a non-empty report (a synthetic omission), which the rule flags.

G4-apps turns this rule green: the API/MCP/CLI projections each project exactly the
capabilities that declare their surface, and the NOTIFY-declaring capabilities are
present in the registry the notify builder reads.
"""

from __future__ import annotations

from typing import cast

from tests.conformance.rulebase import Rule, RuleKind

_LEGACY_MARKERS: tuple[str, ...] = ("OMITS_CAPABILITY",)


def surface_drift() -> list[str]:
    """Every (capability, declared surface) pair missing from its projection (empty = clean)."""
    from valuemaxx.agent_integrability.discovery import build_default_registry
    from valuemaxx.api.app import build_app
    from valuemaxx.capabilities import Surface
    from valuemaxx.cli.main import build_app as build_cli_app
    from valuemaxx.mcp.server import MCPServer

    registry = build_default_registry()

    api_paths = {
        getattr(route, "path", None)
        for route in build_app(registry, api_keys={"k": "t"}, webhook_secret=b"s").routes
    }
    mcp_tools = {tool.name for tool in MCPServer(registry).list_tools()}

    cli_app = build_cli_app()
    cli_commands: set[str] = set()
    for command in cli_app.registered_commands:
        if isinstance(command.name, str):
            cli_commands.add(command.name)
        elif command.callback is not None:
            cli_commands.add(command.callback.__name__)

    notify_caps = {c.name for c in registry.for_surface(Surface.NOTIFY)}

    drift: list[str] = []
    for cap in registry.all():
        if Surface.API in cap.surfaces and f"/{cap.name}" not in api_paths:
            drift.append(f"{cap.name}: declares API but has no route")
        if Surface.MCP in cap.surfaces and cap.name not in mcp_tools:
            drift.append(f"{cap.name}: declares MCP but is not a tool")
        if Surface.CLI in cap.surfaces and cap.name.replace("_", "-") not in cli_commands:
            drift.append(f"{cap.name}: declares CLI but is not a command")
        if Surface.NOTIFY in cap.surfaces and cap.name not in notify_caps:
            drift.append(f"{cap.name}: declares NOTIFY but is not registry-readable")
    return drift


def _flags(subject: object) -> bool:
    # A real drift report (list) is a violation iff it is non-empty; the legacy
    # synthetic negative fixture is a source string carrying the OMITS marker.
    if isinstance(subject, list):
        return len(cast("list[object]", subject)) > 0
    assert isinstance(subject, str)
    return any(marker in subject for marker in _LEGACY_MARKERS)


def _negative_fixture() -> object:
    # A synthetic non-empty drift report (one capability omitted from a surface).
    return ["frobnicate: declares API but has no route"]


def _foundation_subject() -> object:
    return surface_drift()


RULE = Rule(
    name="capability_on_every_declared_surface",
    kind=RuleKind.STATIC,
    green_now=True,
    owner_task="G4-apps",
    flags_violation=_flags,
    negative_fixture=_negative_fixture,
    foundation_subject=_foundation_subject,
)
