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

# The fixed config-AST allowlist (G1-EXIT item 7): the config-shaped / capability-I/O
# pydantic models logic packages legitimately define are NOT domain types — they
# parse config (outcomes.yaml/shared_costs.yaml) or shape one capability's request/
# response. The DOMAIN types they carry still live only in valuemaxx.core; these
# files just describe the wire/config envelope. Allowlisted by file basename so the
# rule doesn't false-positive on them. Any pydantic model OUTSIDE both core and this
# allowlist remains a blocker.
_CONFIG_AST_ALLOWLIST: frozenset[str] = frozenset(
    {
        "capabilities.py",  # capability I/O contracts (request/response envelopes)
        "config.py",  # SDK/package config models
        "schemas.py",  # outcomes.yaml / shared_costs.yaml parse schemas
    }
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
    """Scan every logic package src; return files that illegally declare a model.

    Files on the fixed config-AST allowlist (capability-I/O / config envelopes) are
    permitted to define pydantic models and are skipped (G1-EXIT item 7).
    """
    offenders: list[str] = []
    for pkg in _LOGIC_PACKAGES:
        for py in package_src(pkg).rglob("*.py"):
            if py.name in _CONFIG_AST_ALLOWLIST:
                continue
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
