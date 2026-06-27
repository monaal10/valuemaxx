"""rollup_carries_confidence — every rollup-shaped model carries both H7 fields.

A rollup-shaped model (one whose name ends in ``Rollup``) must carry a
``RollupConfidence`` with both ``minimum_tier`` and ``confidence_distribution``.
``flags_violation`` inspects a pydantic model class. The negative fixture is a
rollup model lacking the confidence; the foundation subject is the real
``RunCostRollup``.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel
from valuemaxx.core.rollup import RollupConfidence, RunCostRollup

from tests.conformance.rulebase import Rule, RuleKind


def _carries_confidence(model: type[BaseModel]) -> bool:
    field = model.model_fields.get("confidence")
    return field is not None and field.annotation is RollupConfidence


def _flags(subject: object) -> bool:
    assert isinstance(subject, type)
    assert issubclass(subject, BaseModel)
    return not _carries_confidence(subject)


class _RogueRollup(BaseModel):
    total_cost_usd: Decimal  # rollup-shaped but no RollupConfidence -> violation


def _negative_fixture() -> object:
    return _RogueRollup


def _foundation_subject() -> object:
    return RunCostRollup


RULE = Rule(
    name="rollup_carries_confidence",
    kind=RuleKind.STATIC,
    green_now=True,
    owner_task="foundation",
    flags_violation=_flags,
    negative_fixture=_negative_fixture,
    foundation_subject=_foundation_subject,
)
