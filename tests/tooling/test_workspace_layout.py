"""F0-TOOLING guardrails — the workspace shape is locked by tests.

These are fast, hermetic config-assertion tests (no subprocess). The heavy gates
(``uv sync``/``pyright``/``ruff``/``lint-imports``) run as their own CI steps;
running them again as pytest subprocesses would be slow and recursive. What is
durable here is the *invariant*: the shared ``valuemaxx`` PEP 420 namespace with
clean bare sub-package names, and the coverage gate, which can never silently drift.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# The single shared namespace. Every package nests its module under `src/valuemaxx/`
# as a PEP 420 namespace package (NO `__init__.py` directly under `valuemaxx/`).
_NAMESPACE = "valuemaxx"
# Each nested sub-package dir must match this (clean bare names, §2).
_SUBPKG_NAME = re.compile(r"^[a-z][a-z_]*$")
# Foreign prefixes / the pre-rename flat naming that must never reappear.
_FORBIDDEN_PREFIXES = ("ai_margin_", "atmx_", "atm_", "valuemaxx_")


def _namespace_roots() -> list[Path]:
    """Every `src/valuemaxx` namespace-root dir across packages/, apps/, sdks/."""
    roots = [REPO_ROOT / "packages", REPO_ROOT / "apps", REPO_ROOT / "sdks"]
    ns_roots: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for src in root.glob("*/src/*"):
            if src.is_dir() and src.name == _NAMESPACE:
                ns_roots.append(src)
    return ns_roots


def test_every_src_top_dir_is_the_valuemaxx_namespace() -> None:
    """Every `src/` top-level dir is the shared `valuemaxx` namespace (nested layout)."""
    roots = [REPO_ROOT / "packages", REPO_ROOT / "apps"]
    bad: list[str] = []
    for root in roots:
        if not root.exists():
            continue
        for src in root.glob("*/src/*"):
            if src.is_dir() and src.name != _NAMESPACE:
                bad.append(str(src.relative_to(REPO_ROOT)))
    assert not bad, f"src top dirs that are not the '{_NAMESPACE}' namespace: {bad}"


def test_namespace_root_has_no_init() -> None:
    """PEP 420: no `__init__.py` directly under any `src/valuemaxx/` (would break merge)."""
    strays = [
        str((ns / "__init__.py").relative_to(REPO_ROOT))
        for ns in _namespace_roots()
        if (ns / "__init__.py").exists()
    ]
    assert not strays, f"stray __init__.py at namespace root breaks the merge: {strays}"


def test_nested_subpackages_use_clean_bare_names() -> None:
    """Each `valuemaxx/<pkg>` is a clean bare name (no prefix) and is a real package."""
    bad: list[str] = []
    for ns in _namespace_roots():
        for sub in ns.iterdir():
            if sub.is_dir() and not _SUBPKG_NAME.match(sub.name):
                bad.append(str(sub.relative_to(REPO_ROOT)))
    assert not bad, f"non-bare nested sub-package names: {bad}"


def test_no_foreign_prefix() -> None:
    """No pre-rename / foreign module prefixes (`atm_`, `valuemaxx_`, ...) anywhere."""
    offenders: list[str] = []
    for root in (REPO_ROOT / "packages", REPO_ROOT / "apps", REPO_ROOT / "sdks"):
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if any(path.name.startswith(p) for p in _FORBIDDEN_PREFIXES):
                offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, f"forbidden module prefixes found: {offenders}"


def test_core_and_capabilities_ship_py_typed() -> None:
    """Every foundation package ships a `py.typed` marker (PEP 561), in the sub-package."""
    for pkg in ("core", "capabilities"):
        marker = REPO_ROOT / "packages" / pkg / "src" / _NAMESPACE / pkg / "py.typed"
        assert marker.exists(), f"missing py.typed for {_NAMESPACE}.{pkg}"


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
    assert "valuemaxx.core" in source
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
