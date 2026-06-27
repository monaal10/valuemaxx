"""dependency_direction — deps flow toward core; no logic->logic (foundation-green).

A logic package may import ``valuemaxx.core`` and ``valuemaxx.capabilities`` but
never another logic package. ``flags_violation`` inspects a python source string
for a cross-logic import. The negative fixture imports a sibling logic package;
the foundation subject is a clean logic-package source.
"""

from __future__ import annotations

import ast

from tests.conformance.astutil import package_src
from tests.conformance.rulebase import Rule, RuleKind

_LOGIC_PACKAGES = (
    "capture",
    "outcomes",
    "attribution",
    "reconciliation",
    "allocation",
    "metrics",
    "eval",
    "onboarding",
    "store",
)


def _logic_imports(source: str) -> set[str]:
    """The set of valuemaxx logic sub-packages imported by this source."""
    tree = ast.parse(source)
    found: set[str] = set()
    for node in ast.walk(tree):
        modules: list[str] = []
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.append(node.module)
        elif isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        for mod in modules:
            parts = mod.split(".")
            if len(parts) >= 2 and parts[0] == "valuemaxx" and parts[1] in _LOGIC_PACKAGES:
                found.add(parts[1])
    return found


def _flags(subject: object) -> bool:
    assert isinstance(subject, str)
    return bool(_logic_imports(subject))


def _negative_fixture() -> object:
    # outcomes illegally reaching into attribution
    return "from valuemaxx.attribution.binding import resolve\n"


def _foundation_subject() -> object:
    return (package_src("outcomes") / "__init__.py").read_text()


def foundation_logic_cross_imports() -> dict[str, set[str]]:
    """Scan each logic package; return any that import a sibling logic package."""
    offenders: dict[str, set[str]] = {}
    for pkg in _LOGIC_PACKAGES:
        for py in package_src(pkg).rglob("*.py"):
            imported = _logic_imports(py.read_text()) - {pkg}
            if imported:
                offenders.setdefault(pkg, set()).update(imported)
    return offenders


RULE = Rule(
    name="dependency_direction",
    kind=RuleKind.STATIC,
    green_now=True,
    owner_task="foundation",
    flags_violation=_flags,
    negative_fixture=_negative_fixture,
    foundation_subject=_foundation_subject,
)
