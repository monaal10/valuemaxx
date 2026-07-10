"""`valuemaxx onboard`/`init` work without the backend ([cli]) deps; `up` degrades cleanly.

The design: `pip install valuemaxx` (base) ships the SDK + the `valuemaxx` command with
`onboard` + `init` (light: tree-sitter/yaml/typer), symmetric with `npm install valuemaxx`.
The backend (`up` + query commands) is the heavy `[cli]` extra. These tests assert the
CLI app builds and `onboard`/`init` run WITHOUT importing the backend, and that `up` prints
a friendly install hint rather than a traceback when the backend deps are absent — proven
here by simulating a missing `fastapi` during the lazy import inside `up`.
"""

from __future__ import annotations

import builtins
from typing import TYPE_CHECKING

from typer.testing import CliRunner
from valuemaxx.cli.main import build_app

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence
    from types import ModuleType

    import pytest

_runner = CliRunner()
_REAL_IMPORT = builtins.__import__
# Backend module prefixes the base install lacks; importing one simulates the base install.
_BACKEND = frozenset({"fastapi", "uvicorn", "sqlalchemy", "alembic"})


def _backend_absent_import() -> Callable[..., ModuleType]:
    """An __import__ replacement that raises ModuleNotFoundError for any backend module."""

    def _fake(
        name: str,
        globals: Mapping[str, object] | None = None,  # noqa: A002  # matches __import__ signature
        locals: Mapping[str, object] | None = None,  # noqa: A002  # matches __import__ signature
        fromlist: Sequence[str] = (),
        level: int = 0,
    ) -> ModuleType:
        if name.split(".")[0] in _BACKEND or name.startswith("valuemaxx.server"):
            raise ModuleNotFoundError(f"No module named {name!r}", name=name.split(".")[0])
        return _REAL_IMPORT(name, globals, locals, fromlist, level)

    return _fake


def test_onboard_runs_without_backend_imports(monkeypatch: pytest.MonkeyPatch) -> None:
    """`valuemaxx onboard` runs even if the backend deps can't import (base install)."""
    monkeypatch.setattr(builtins, "__import__", _backend_absent_import())
    app = build_app()  # must not raise even though the backend can't import
    result = _runner.invoke(app, ["onboard", "--help"])
    assert result.exit_code == 0
    assert "onboard" in result.stdout.lower()


def test_up_without_backend_prints_friendly_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    """`valuemaxx up` with the backend deps absent -> install hint + exit 1, not a traceback."""
    monkeypatch.setattr(builtins, "__import__", _backend_absent_import())
    app = build_app()
    result = _runner.invoke(app, ["up"])
    assert result.exit_code == 1
    combined = result.stdout + (result.stderr or "")
    assert "[cli]" in combined
    assert "Traceback" not in combined
