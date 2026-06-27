"""granularity_labeled — every CostEvent construction sets capture_granularity (GREEN; CAPTURE).

A CostEvent emitted without ``capture_granularity`` would hide whether the number
is per-attempt or the degraded per-call fallback (§5.2). This rule AST-scans a
source for any ``CostEvent(...)`` construction and flags it if the
``capture_granularity`` keyword is absent.

Authored RED-but-meaningful, now GREEN: ``flags_violation`` flags the negative
fixture (a ``CostEvent(...)`` call with no ``capture_granularity``), proving the
rule logic is real; the foundation subject is the real capture transport-patch
path (``valuemaxx.capture``'s ``patch.py``), which always stamps it.
"""

from __future__ import annotations

import ast

from tests.conformance.astutil import package_src
from tests.conformance.rulebase import Rule, RuleKind

_COST_EVENT = "CostEvent"
_REQUIRED_KW = "capture_granularity"


def _constructs_cost_event_without_granularity(source: str) -> bool:
    """True if any ``CostEvent(...)`` call in ``source`` omits ``capture_granularity``."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        callee = (
            func.id
            if isinstance(func, ast.Name)
            else func.attr
            if isinstance(func, ast.Attribute)
            else None
        )
        if callee != _COST_EVENT:
            continue
        kwargs = {kw.arg for kw in node.keywords if kw.arg is not None}
        if _REQUIRED_KW not in kwargs:
            return True
    return False


def _flags(subject: object) -> bool:
    assert isinstance(subject, str)
    return _constructs_cost_event_without_granularity(subject)


def _negative_fixture() -> object:
    # a CostEvent constructed without capture_granularity -> violation
    return (
        "CostEvent(tenant_id=t, id=i, run_id=r, attempt_id=a, provider=p, model=m,\n"
        "          tokens=tv, provenance=pl, cost_usd=c, is_streaming=False,\n"
        "          partial_recovered=False, billing_uncertain_abort=False,\n"
        "          provenance_warnings=(), occurred_at=now)\n"
    )


def _foundation_subject() -> object:
    # the real capture path that constructs CostEvents from transport attempts.
    return (package_src("capture") / "patch.py").read_text()


RULE = Rule(
    name="granularity_labeled",
    kind=RuleKind.STATIC,
    green_now=True,
    owner_task="CAPTURE",
    flags_violation=_flags,
    negative_fixture=_negative_fixture,
    foundation_subject=_foundation_subject,
)
