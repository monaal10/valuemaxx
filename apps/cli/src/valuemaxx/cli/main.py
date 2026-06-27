"""The ``valuemaxx`` CLI — a thin projection plus the three operator commands.

``build_app`` assembles the typer app: it mounts every ``Surface.CLI`` capability as
a command (thin projection of the registry) and adds the three operator commands,
implemented for real:

* ``valuemaxx up`` — boot the backend. Builds the assembly app via
  :func:`~valuemaxx.server.app.create_app` and serves it with uvicorn (the store
  opens + migrations run on ASGI startup). Honors ``--db`` / ``DATABASE_URL`` and
  ``--host`` / ``--port`` (default ``127.0.0.1:8000``); prints the served URL. This is
  the ``pip install -> valuemaxx up -> it works`` path.
* ``valuemaxx init`` — detect the host framework, then EMIT the SDK ``init()``
  scaffold as a reviewable unified diff (review-only by default). ``--apply`` writes
  the wiring via the reversible SDK scaffolder
  (:mod:`valuemaxx.sdk.scaffold`) — never an unconfirmed auto-edit.
* ``valuemaxx onboard`` — run the real onboarding pipeline
  (:func:`~valuemaxx.onboarding.scan.scan_codebase` ->
  :func:`~valuemaxx.onboarding.propose.build_proposal` ->
  :func:`~valuemaxx.onboarding.render.render_outcomes_yaml` +
  :func:`~valuemaxx.onboarding.diff.build_reviewable_diff`), printing the proposed
  ``outcomes.yaml`` and the hunks-only reviewable diff. The candidate rules are
  UNCONFIRMED until a human reviews the diff.

Every capability command prints its rollup output with ``minimum_tier`` (H7) via
:mod:`valuemaxx.cli.render`; capability commands require ``--tenant``.
"""

from __future__ import annotations

import difflib
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import typer
import uvicorn
from valuemaxx.agent_integrability.discovery import build_default_registry
from valuemaxx.cli.projection import mount_capabilities
from valuemaxx.onboarding.diff import build_reviewable_diff
from valuemaxx.onboarding.propose import build_proposal
from valuemaxx.onboarding.render import render_outcomes_yaml
from valuemaxx.onboarding.scan import scan_codebase
from valuemaxx.sdk import scaffold
from valuemaxx.server.app import create_app
from valuemaxx.server.settings import ServerSettings

if TYPE_CHECKING:
    from fastapi import FastAPI
    from valuemaxx.onboarding.capabilities import ReviewableDiff

# Frameworks the init scaffolder can detect, by a marker file in the target repo.
# The marker file doubles as the entry file the SDK ``init()`` call is injected into
# (Python entrypoints only; an Express ``package.json`` is detected but not injected).
_FRAMEWORK_MARKERS: tuple[tuple[str, str], ...] = (
    ("fastapi", "main.py"),
    ("django", "manage.py"),
    ("express", "package.json"),
)

# The env-var names the scaffolded ``init()`` reads its credentials from. These match
# the SDK's documented bootstrap variables; the wiring never embeds a literal secret.
_TENANT_ENV = "VALUEMAXX_TENANT_ID"
_INGEST_ENV = "VALUEMAXX_INGEST_KEY"

# Module-level typer Option singletons (typer evaluates these as defaults; defining
# them once avoids the B008 "call in argument default" pitfall).
_REPO_OPTION = typer.Option(Path(), "--repo", help="The target repository.")
_DB_OPTION = typer.Option(
    None,
    "--db",
    help="Backend store URL (default: embedded SQLite; or set DATABASE_URL).",
)
_HOST_OPTION = typer.Option("127.0.0.1", "--host", help="Bind host for the server.")
_PORT_OPTION = typer.Option(8000, "--port", help="Bind port for the server.")
_APPLY_OPTION = typer.Option(
    False,
    "--apply",
    help="Write the scaffold into the entry file (default: emit a review-only diff).",
)


def _detect_framework(repo: Path) -> str:
    """Best-effort framework detection from marker files (stub heuristic)."""
    for framework, marker in _FRAMEWORK_MARKERS:
        if (repo / marker).exists():
            return framework
    return "unknown"


def _entry_file(repo: Path) -> Path | None:
    """The Python entry file the SDK ``init()`` is injected into, if one is present.

    Returns the first ``.py`` marker file that exists (``main.py`` / ``manage.py``);
    a non-Python marker (Express ``package.json``) yields ``None`` — the Python SDK
    scaffolder only edits Python entrypoints.
    """
    for _framework, marker in _FRAMEWORK_MARKERS:
        candidate = repo / marker
        if marker.endswith(".py") and candidate.exists():
            return candidate
    return None


def _scaffold_preview(entry: Path) -> str:
    """The scaffolded text the SDK injector WOULD produce, without touching ``entry``.

    Copies the entry file into a throwaway temp dir, runs the real
    :func:`valuemaxx.sdk.scaffold.inject` on the copy, and reads it back — so the diff
    is exactly what ``--apply`` would write, with zero risk to the user's file.
    """
    original = entry.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as tmp:
        probe = Path(tmp) / entry.name
        probe.write_text(original, encoding="utf-8")
        scaffold.inject(probe, tenant_env=_TENANT_ENV, ingest_env=_INGEST_ENV)
        return probe.read_text(encoding="utf-8")


def _unified_diff(*, path: str, before: str, after: str) -> str:
    """A unified diff between ``before`` and ``after`` for ``path`` (empty if identical)."""
    diff = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
    )
    return "".join(diff)


def init(repo: Path = _REPO_OPTION, *, apply: bool = _APPLY_OPTION) -> None:
    """Scaffold the SDK init: detect the framework and emit a reviewable diff.

    Detects the host framework, then renders the ``valuemaxx.init()`` injection as a
    unified diff against the entry file (review-only by default — never an unconfirmed
    auto-edit). With ``--apply`` the reversible SDK scaffolder writes the wiring in
    place (undo with ``valuemaxx.sdk.scaffold.revert``).
    """
    framework = _detect_framework(repo)
    typer.echo(f"valuemaxx init: detected framework={framework}")
    entry = _entry_file(repo)
    if entry is None:
        typer.echo(
            "init: no Python entrypoint found to scaffold; "
            "add a main.py/manage.py or wire `valuemaxx.init()` by hand."
        )
        return

    rel = entry.name
    before = entry.read_text(encoding="utf-8")
    if apply:
        scaffold.inject(entry, tenant_env=_TENANT_ENV, ingest_env=_INGEST_ENV)
        typer.echo(f"init: scaffolded `valuemaxx.init()` into {rel} (reversible).")
        return

    after = _scaffold_preview(entry)
    diff = _unified_diff(path=rel, before=before, after=after)
    if not diff:
        typer.echo(f"init: {rel} is already scaffolded (no changes).")
        return
    typer.echo(f"init: reviewable diff for {rel} (apply with --apply):")
    typer.echo(diff)


def _serve(app: FastAPI, *, host: str, port: int) -> None:  # pragma: no cover - binds a socket
    """Serve ``app`` with uvicorn until interrupted (the real socket bind).

    Factored out as a seam so the ``up`` command's wiring (settings -> create_app ->
    serve) is unit-testable without binding a socket; tests patch this function.
    """
    uvicorn.Server(uvicorn.Config(app, host=host, port=port)).run()


def _resolve_database_url(db: str | None) -> str | None:
    """The store URL for ``up``: explicit ``--db`` wins, else ``DATABASE_URL`` env.

    Returns ``None`` to let :class:`~valuemaxx.server.settings.ServerSettings` apply
    its embedded-SQLite default (``VALUEMAXX_DATABASE_URL`` / the field default).
    """
    if db is not None:
        return db
    return os.environ.get("DATABASE_URL")


def up(
    db: str | None = _DB_OPTION,
    *,
    host: str = _HOST_OPTION,
    port: int = _PORT_OPTION,
) -> None:
    """Start the backend: build the assembly app and serve it with uvicorn.

    Resolves the store URL (``--db`` > ``DATABASE_URL`` env > embedded SQLite),
    builds the FastAPI assembly via :func:`~valuemaxx.server.app.create_app` (the
    store opens and migrations run on ASGI startup), prints the served URL, and serves
    it on ``host``/``port`` (default ``127.0.0.1:8000``).
    """
    database_url = _resolve_database_url(db)
    settings = (
        ServerSettings(database_url=database_url) if database_url is not None else ServerSettings()
    )
    app = create_app(settings)
    typer.echo(f"valuemaxx up: serving on http://{host}:{port} (db={settings.database_url})")
    _serve(app, host=host, port=port)


class _OnboardingSignalMapper:
    """System-owned :class:`~valuemaxx.core.SignalClassMapper` for onboarding scans.

    Maps an onboarding scan-site match kind to its signal class. The signal class is
    SYSTEM-owned, never user-set (``declared`` is advisory only, ignored): a webhook
    or an in-process status/ORM write may confirm an outcome, but a bare external
    write is only ``action_attempted`` — a function attempt can never masquerade as a
    confirmed outcome (honesty axis §4).
    """

    _CONFIRMING = frozenset({"status_setter", "mark_function", "orm_write", "webhook"})

    def map_signal(self, *, match_kind: str, declared: str) -> str:
        """Return the system-assigned signal class for an onboarding match kind."""
        _ = declared  # advisory only; the system owns the result
        if match_kind in self._CONFIRMING:
            return "outcome_confirmed"
        return "action_attempted"


def _render_diff(diff: ReviewableDiff) -> str:
    """Render a hunks-only :class:`ReviewableDiff` as reviewable text."""
    lines: list[str] = []
    for hunk in diff.hunks:
        lines.append(f"--- {hunk.file}")
        lines.append(f"+++ {hunk.file}")
        lines.append(hunk.header)
        lines.extend(hunk.lines)
    return "\n".join(lines)


def onboard(repo: Path = _REPO_OPTION) -> None:
    """Run the onboarding pipeline: scan -> propose -> render -> diff (reviewable).

    Scans the repo for run boundaries and outcome sites, builds an UNCONFIRMED
    proposal, and prints the rendered ``outcomes.yaml`` plus a hunks-only reviewable
    diff (the ``init()`` inserts + the generated config). The candidate outcome rules
    are UNCONFIRMED until a human reviews the diff — they are never auto-applied.
    """
    typer.echo(f"valuemaxx onboard: scanning {repo} -> propose -> render -> diff.")
    scan = scan_codebase(repo)
    proposal = build_proposal(scan, signal_mapper=_OnboardingSignalMapper())
    outcomes_yaml = render_outcomes_yaml(proposal)
    diff = build_reviewable_diff(proposal, scan)

    typer.echo("\n# --- proposed outcomes.yaml ---")
    typer.echo(outcomes_yaml)
    typer.echo("# --- reviewable diff ---")
    typer.echo(_render_diff(diff))
    typer.echo("\nonboard: candidate outcome rules are UNCONFIRMED until you review the diff.")


def build_app() -> typer.Typer:
    """Build the ``valuemaxx`` typer app: capability commands + init/up/onboard."""
    app = typer.Typer(
        name="valuemaxx",
        help="valuemaxx — AI margin intelligence: cost-per-outcome with confidence.",
        no_args_is_help=True,
        add_completion=False,
    )
    app.command(name="init")(init)
    app.command(name="up")(up)
    app.command(name="onboard")(onboard)
    mount_capabilities(app, build_default_registry())
    return app


app = build_app()


def main() -> None:
    """Console-script entry point for the ``valuemaxx`` CLI."""
    app()


__all__ = ["app", "build_app", "init", "main", "onboard", "up"]
