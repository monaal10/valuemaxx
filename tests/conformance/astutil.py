"""Small AST/import helpers shared by the static conformance rules."""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES_DIR = REPO_ROOT / "packages"


def package_src(pkg: str) -> Path:
    """The src namespace dir for a logic package, e.g. valuemaxx/core."""
    return PACKAGES_DIR / pkg / "src" / "valuemaxx" / pkg


def imported_roots(source: str) -> set[str]:
    """The set of top-level import roots in a Python source string."""
    tree = ast.parse(source)
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def defines_pydantic_model(source: str) -> bool:
    """True if the source declares a class that looks like a pydantic model."""
    tree = ast.parse(source)
    model_bases = {"BaseModel", "StrictModel", "TenantScopedModel"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            base_names = {b.id for b in node.bases if isinstance(b, ast.Name)}
            base_names |= {b.attr for b in node.bases if isinstance(b, ast.Attribute)}
            if base_names & model_bases:
                return True
    return False


__all__ = [
    "PACKAGES_DIR",
    "REPO_ROOT",
    "defines_pydantic_model",
    "imported_roots",
    "package_src",
]
