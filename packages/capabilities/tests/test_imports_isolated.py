"""F0-CAPS: valuemaxx.capabilities imports only stdlib + pydantic + typing (H6)."""

from __future__ import annotations

import ast
from pathlib import Path

import valuemaxx.capabilities

_SRC_DIR = Path(valuemaxx.capabilities.__file__).parent

# Allowed top-level import roots: stdlib + pydantic + typing + the package itself.
_FORBIDDEN_ROOTS = {
    "fastapi",
    "typer",
    "mcp",
    "valuemaxx.core",
    "valuemaxx.capture",
    "valuemaxx.outcomes",
    "valuemaxx.attribution",
    "valuemaxx.reconciliation",
    "valuemaxx.allocation",
    "valuemaxx.metrics",
    "valuemaxx.eval",
    "valuemaxx.onboarding",
    "valuemaxx.store",
}


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_capabilities_imports_only_stdlib_pydantic_typing() -> None:
    """T-CAP-6: no logic package or surface framework imported anywhere in the package."""
    offenders: dict[str, set[str]] = {}
    for py in _SRC_DIR.rglob("*.py"):
        bad = _imported_roots(py) & _FORBIDDEN_ROOTS
        if bad:
            offenders[py.name] = bad
    assert not offenders, f"forbidden imports in valuemaxx.capabilities: {offenders}"
