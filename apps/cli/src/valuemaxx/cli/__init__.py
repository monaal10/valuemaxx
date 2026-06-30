"""valuemaxx.cli — the ``valuemaxx`` CLI (thin registry projection + scaffolder).

Each ``Surface.CLI`` capability becomes a typer command; the three operator commands
``init`` / ``up`` / ``onboard`` are always present. Every rollup-returning command
prints ``minimum_tier`` + the confidence distribution (H7), so a number never prints
without its conservative confidence label.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

# Importing this package must stay dependency-light: `valuemaxx.cli.main` pulls in typer /
# uvicorn / fastapi / the server, which a bare `pip install valuemaxx` (no `[cli]` extra)
# does not have. The console-script wrapper (`valuemaxx.cli._entry`) imports this package,
# so an eager `from .main import …` here would crash with a raw ModuleNotFoundError before
# the wrapper's friendly install-hint guard runs. PEP 562 lazy attribute access defers the
# heavy import to first *use* of `app`/`build_app`/`main`/render helpers — so the package
# imports cheaply, and the wrapper can catch the missing-extra error and print the hint.
if TYPE_CHECKING:
    from valuemaxx.cli.main import app, build_app, main
    from valuemaxx.cli.render import is_rollup_output, render_output

_LAZY: dict[str, str] = {
    "app": "valuemaxx.cli.main",
    "build_app": "valuemaxx.cli.main",
    "main": "valuemaxx.cli.main",
    "is_rollup_output": "valuemaxx.cli.render",
    "render_output": "valuemaxx.cli.render",
}


def __getattr__(name: str) -> Any:  # noqa: ANN401  # PEP 562 module-level dynamic attr
    module = _LAZY.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    return getattr(importlib.import_module(module), name)


__all__ = ["app", "build_app", "is_rollup_output", "main", "render_output"]
