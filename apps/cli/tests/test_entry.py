"""The console-script entry wrapper turns a missing-[cli]-extra into a friendly hint.

Regression for a real UX bug: the published entry point used to target
``valuemaxx.cli.main:main`` directly, so a bare ``pip install valuemaxx`` (no ``[cli]``
extra) made ``valuemaxx <anything>`` crash with a raw
``ModuleNotFoundError: No module named 'typer'`` traceback — which reads as a broken
install, not a missing extra. The entry point now targets :func:`valuemaxx.cli._entry.main`,
which catches a missing-CLI-extra import error and prints one actionable line.

These tests lock that in WITHOUT uninstalling typer: they monkeypatch the lazy import to
raise the relevant ImportError, and assert (1) a missing CLI-extra dep -> friendly stderr
+ SystemExit(1), and (2) a genuinely-unexpected missing module re-raises (never silently
swallowed).
"""

from __future__ import annotations

import builtins
from typing import TYPE_CHECKING

import pytest
from valuemaxx.cli import _entry

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence
    from types import ModuleType

_REAL_IMPORT = builtins.__import__


def _import_raising(missing: str) -> Callable[..., ModuleType]:
    """An __import__ replacement that raises ModuleNotFoundError for `missing`."""

    def _fake(
        name: str,
        globals: Mapping[str, object] | None = None,  # noqa: A002  # matches __import__ signature
        locals: Mapping[str, object] | None = None,  # noqa: A002  # matches __import__ signature
        fromlist: Sequence[str] = (),
        level: int = 0,
    ) -> ModuleType:
        if name == "valuemaxx.cli.main" or name.split(".")[0] == missing:
            raise ModuleNotFoundError(f"No module named {missing!r}", name=missing)
        return _REAL_IMPORT(name, globals, locals, fromlist, level)

    return _fake


def test_missing_cli_extra_prints_hint_and_exits(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A missing CLI-extra dependency (typer) -> a one-line install hint + exit 1."""
    monkeypatch.setattr(builtins, "__import__", _import_raising("typer"))
    with pytest.raises(SystemExit) as exc:
        _entry.main()
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "[cli]" in err
    assert 'pip install "valuemaxx[cli]"' in err
    assert "Traceback" not in err  # never a raw stack trace


def test_unexpected_missing_module_reraises(monkeypatch: pytest.MonkeyPatch) -> None:
    """A missing module that is NOT a CLI extra is a real error — re-raise, don't swallow."""
    monkeypatch.setattr(builtins, "__import__", _import_raising("some_unrelated_pkg"))
    with pytest.raises(ModuleNotFoundError, match="some_unrelated_pkg"):
        _entry.main()
