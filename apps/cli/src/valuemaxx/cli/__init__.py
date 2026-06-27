"""valuemaxx.cli — the ``valuemaxx`` CLI (thin registry projection + scaffolder).

Each ``Surface.CLI`` capability becomes a typer command; the three operator commands
``init`` / ``up`` / ``onboard`` are always present. Every rollup-returning command
prints ``minimum_tier`` + the confidence distribution (H7), so a number never prints
without its conservative confidence label.
"""

from __future__ import annotations

from valuemaxx.cli.main import app, build_app, main
from valuemaxx.cli.render import is_rollup_output, render_output

__all__ = ["app", "build_app", "is_rollup_output", "main", "render_output"]
