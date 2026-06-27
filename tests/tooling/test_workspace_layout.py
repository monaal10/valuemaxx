"""F0-TOOLING guardrails — the workspace shape is locked by tests.

These are fast, hermetic config-assertion tests (no subprocess). The heavy gates
(``uv sync``/``pyright``/``ruff``/``lint-imports``) run as their own CI steps;
running them again as pytest subprocesses would be slow and recursive. What is
durable here is the *invariant*: the canonical ``atm_`` prefix and the coverage
gate, which can never silently drift.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Every src top-level package directory must match this (canonical naming, §2).
_ATM_PREFIX = re.compile(r"^atm_[a-z_]+$")
# Foreign prefixes that must never appear (the build plan locks `atm_`).
_FORBIDDEN_PREFIXES = ("ai_margin_", "atmx_")


def _src_top_dirs() -> list[Path]:
    """Every `src/<pkg>` top-level package dir across packages/, apps/, sdks/."""
    roots = [REPO_ROOT / "packages", REPO_ROOT / "apps", REPO_ROOT / "sdks"]
    top_dirs: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for src in root.glob("*/src/*"):
            if src.is_dir():
                top_dirs.append(src)
    return top_dirs


def test_every_src_top_dir_uses_atm_prefix() -> None:
    """T-TOOL: every src top-level package matches `^atm_[a-z_]+$`."""
    top_dirs = _src_top_dirs()
    assert top_dirs, "expected at least the core/capabilities src packages to exist"
    bad = [d.name for d in top_dirs if not _ATM_PREFIX.match(d.name)]
    assert not bad, f"non-atm src package dirs found: {bad}"


def test_no_foreign_prefix() -> None:
    """T-TOOL `test_no_foreign_prefix`: no `ai_margin_*` / `atmx_*` modules anywhere."""
    offenders: list[str] = []
    for root in (REPO_ROOT / "packages", REPO_ROOT / "apps", REPO_ROOT / "sdks"):
        if not root.exists():
            continue
        for path in root.rglob("*"):
            name = path.name
            if any(name.startswith(p) for p in _FORBIDDEN_PREFIXES):
                offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, f"forbidden module prefixes found: {offenders}"


def test_core_and_capabilities_ship_py_typed() -> None:
    """Every foundation package ships a `py.typed` marker (PEP 561)."""
    for pkg in ("core", "capabilities"):
        marker = REPO_ROOT / "packages" / pkg / "src" / f"atm_{pkg}" / "py.typed"
        assert marker.exists(), f"missing py.typed for atm_{pkg}"


def test_coverage_gate_is_90() -> None:
    """T-TOOL `test_coverage_gate_is_90`: fail_under==90 and branch coverage on."""
    import configparser

    cfg = configparser.ConfigParser()
    cfg.read(REPO_ROOT / ".coveragerc")
    assert cfg.getboolean("run", "branch") is True
    assert cfg.getint("report", "fail_under") == 90


def test_coverage_scoped_to_core_spine() -> None:
    """The coverage source is the core typed spine, with apps/generated omitted."""
    import configparser

    cfg = configparser.ConfigParser()
    cfg.read(REPO_ROOT / ".coveragerc")
    source = cfg.get("run", "source")
    assert "atm_core" in source
    omit = cfg.get("run", "omit")
    assert "apps/*" in omit


def test_tiktoken_banned_for_cost() -> None:
    """ruff.toml bans `tiktoken` repo-wide (no_tiktoken_for_cost guardrail)."""
    ruff_cfg = tomllib.loads((REPO_ROOT / "ruff.toml").read_text())
    banned = ruff_cfg["lint"]["flake8-tidy-imports"]["banned-api"]
    assert "tiktoken" in banned


def test_workspace_members_declared() -> None:
    """The uv workspace declares packages/, apps/, and the python SDK as members."""
    root = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    members = root["tool"]["uv"]["workspace"]["members"]
    assert "packages/*" in members
    assert "apps/*" in members
    assert "sdks/python" in members
