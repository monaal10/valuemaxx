"""honesty_provenance_set (M1) — every cost-bearing field carries a ProvenanceLabel.

A cost-bearing model that exposes a money field without a ``provenance`` of type
``ProvenanceLabel`` is a violation. ``flags_violation`` inspects a pydantic model
class. The negative fixture is a cost model lacking a ProvenanceLabel; the
foundation subject is the real ``CostEvent`` (which carries one).
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel
from valuemaxx.core.cost import CostEvent
from valuemaxx.core.provenance import ProvenanceLabel

from tests.conformance.rulebase import Rule, RuleKind

_MONEY_HINT = ("cost", "amount", "usd", "total", "billed", "estimated")


def _has_money_field(model: type[BaseModel]) -> bool:
    for name, field in model.model_fields.items():
        if any(h in name.lower() for h in _MONEY_HINT):
            return True
        if field.annotation in (Decimal, Decimal | None):
            return True
    return False


def _has_provenance_label(model: type[BaseModel]) -> bool:
    field = model.model_fields.get("provenance")
    return field is not None and field.annotation is ProvenanceLabel


def _flags(subject: object) -> bool:
    assert isinstance(subject, type)
    assert issubclass(subject, BaseModel)
    return _has_money_field(subject) and not _has_provenance_label(subject)


class _RogueCost(BaseModel):
    cost_usd: Decimal  # money but no ProvenanceLabel -> violation


def _negative_fixture() -> object:
    return _RogueCost


def _foundation_subject() -> object:
    return CostEvent


RULE = Rule(
    name="honesty_provenance_set",
    kind=RuleKind.STATIC,
    green_now=True,
    owner_task="foundation",
    flags_violation=_flags,
    negative_fixture=_negative_fixture,
    foundation_subject=_foundation_subject,
)
