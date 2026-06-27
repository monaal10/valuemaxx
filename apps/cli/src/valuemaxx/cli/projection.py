"""Project the capability registry onto typer commands (thin projection, §3/H5).

For each capability declaring ``Surface.CLI`` this registers one typer command on
the app. The command takes a required ``--tenant`` (no untenanted invocation) and a
``--json-input`` carrying the capability input model as JSON; it validates the input
against the model, invokes the handler, and prints the rendered output. Rollup
outputs always print ``minimum_tier`` (see :mod:`valuemaxx.cli.render`).

The command name is the capability name with underscores turned into hyphens (the
typer/CLI idiom); the original capability name is still the JSON contract.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import typer
from valuemaxx.capabilities import Surface
from valuemaxx.cli.render import render_output

if TYPE_CHECKING:
    from collections.abc import Callable

    from valuemaxx.capabilities import AnyCapability, Registry

# Module-level typer Option singletons (typer reads these as defaults; defining them
# once avoids the B008 "call in argument default" pitfall).
_TENANT_OPTION = typer.Option(..., "--tenant", help="The tenant id (required).")
_JSON_INPUT_OPTION = typer.Option("{}", "--json-input", help="The capability input as JSON.")


def _command_name(capability_name: str) -> str:
    """The CLI command name for a capability (underscores -> hyphens)."""
    return capability_name.replace("_", "-")


def _make_command(cap: AnyCapability) -> Callable[[str, str], None]:
    """Build the typer callback for one capability command."""

    def command(
        tenant: str = _TENANT_OPTION,
        json_input: str = _JSON_INPUT_OPTION,
    ) -> None:
        import json as _json

        raw: object = _json.loads(json_input)
        if isinstance(raw, dict) and "tenant_id" not in raw:
            raw["tenant_id"] = tenant
        request = cap.input_model.model_validate(raw)
        response = cap.handler(request)
        typer.echo(render_output(response))

    command.__doc__ = cap.description
    return command


def mount_capabilities(app: typer.Typer, registry: Registry) -> None:
    """Register every ``Surface.CLI`` capability as a command on ``app``."""
    for cap in registry.for_surface(Surface.CLI):
        app.command(name=_command_name(cap.name), help=cap.description)(_make_command(cap))


__all__ = ["mount_capabilities"]
