"""Discover every conformance ``rule_*.py`` module and expose its ``RULE``."""

from __future__ import annotations

import importlib
import pkgutil
from typing import TYPE_CHECKING

import tests.conformance.behavioral as behavioral_pkg
import tests.conformance.static as static_pkg

if TYPE_CHECKING:
    from types import ModuleType

    from tests.conformance.rulebase import Rule


def _rules_in(package: ModuleType) -> list[Rule]:
    rules: list[Rule] = []
    for info in pkgutil.iter_modules(package.__path__):
        if not info.name.startswith("rule_"):
            continue
        module = importlib.import_module(f"{package.__name__}.{info.name}")
        rule = getattr(module, "RULE", None)
        if rule is not None:
            rules.append(rule)
    return rules


def all_rules() -> list[Rule]:
    """Every declared conformance rule (static + behavioral), sorted by name."""
    rules = _rules_in(static_pkg) + _rules_in(behavioral_pkg)
    return sorted(rules, key=lambda r: r.name)


__all__ = ["all_rules"]
