"""no_type_outside_core — domain types live only in valuemaxx.core (foundation-green).

A logic/app package that declares a pydantic *domain* model (outside a fixed
config-AST allowlist) violates the single-source-of-truth rule. ``flags_violation``
inspects a python source string. The negative fixture is a synthetic logic module
that declares a domain model; the foundation subject is a real, clean logic-package
source (an empty skeleton). A separate scan-the-tree assertion lives in the rule's
own test below.
"""

from __future__ import annotations

from tests.conformance.astutil import defines_pydantic_model, package_src
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


def _flags(subject: object) -> bool:
    assert isinstance(subject, str)
    return defines_pydantic_model(subject)


def _negative_fixture() -> object:
    return "from pydantic import BaseModel\nclass RogueCostEvent(BaseModel):\n    amount: int\n"


def _foundation_subject() -> object:
    # A real, clean logic-package source (the skeleton __init__) declares no model.
    return (package_src("capture") / "__init__.py").read_text()


def foundation_has_no_stray_domain_models() -> list[str]:
    """Scan every logic package src; return files that illegally declare a model."""
    offenders: list[str] = []
    for pkg in _LOGIC_PACKAGES:
        for py in package_src(pkg).rglob("*.py"):
            if defines_pydantic_model(py.read_text()):
                offenders.append(str(py))
    return offenders


RULE = Rule(
    name="no_type_outside_core",
    kind=RuleKind.STATIC,
    green_now=True,
    owner_task="foundation",
    flags_violation=_flags,
    negative_fixture=_negative_fixture,
    foundation_subject=_foundation_subject,
)
