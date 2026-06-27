"""Eval models — BYO-key safety + no auto-switch + honest grade cap (§8).

Hard safety rules encoded as types:
  * :class:`ProviderKeyRef` carries only a ``secret_ref`` (env var name / ARN) —
    NO plaintext field (no ``key``/``api_key``/``secret_value``). Keys are never
    persisted, never logged, never returned by a read API (§8.5, C3).
  * :class:`EvalRecommendation.auto_switch` is ``Literal[False]`` — auto-switching
    is unrepresentable; a recommendation is evidence for a human decision (§8.6).
  * ``grade_cap_invariant``: a ``RELIABLE`` grade is constructible only off an
    ``outcome_label`` or ``human_labeled`` rung; judge/reference are capped at
    ``directional`` (§8.2).
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import model_validator
from valuemaxx.core.base import StrictModel, TenantScopedModel
from valuemaxx.core.enums import EvalGrade, LabelSource

_RELIABLE_LABEL_SOURCES = frozenset({LabelSource.OUTCOME_LABEL, LabelSource.HUMAN_LABELED})


class ProviderKeyRef(StrictModel):
    """A reference to a provider key — by env var name / ARN, never plaintext (§8.5)."""

    provider: str
    secret_ref: str


class CostGatePhase(StrEnum):
    """The two cost-gate phases (§8.5 M2): smoke first, confirmation second."""

    SMOKE = "smoke"
    CONFIRMATION = "confirmation"


class CostEstimate(StrictModel):
    """An exact per-candidate cost estimate for a gate phase (the estimate IS consent)."""

    phase: CostGatePhase
    provider: str
    model: str
    estimated_usd: Decimal
    n_cases: int


class EvalCase(StrictModel):
    """One eval case drawn from real traces (§8.3)."""

    id: str
    inputs: Mapping[str, object]
    label_source: LabelSource
    source_trace_id: str | None


class EvalDataset(TenantScopedModel):
    """A versioned, stratified eval dataset built from real traces (§8.3)."""

    id: str
    name: str
    version: int
    cases: tuple[EvalCase, ...]


class ModelCandidate(StrictModel):
    """A candidate model in the search, costed fully-loaded (§8.4)."""

    provider: str
    model: str
    key_ref: ProviderKeyRef


class EvalRecommendation(TenantScopedModel):
    """The recommendation artifact — confidence-labeled, never auto-applied (§8.6)."""

    recommended_model: str | None
    incumbent_model: str
    grade: EvalGrade
    label_source: LabelSource
    parity_ci95: tuple[Decimal, Decimal]
    latency_p50_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    sample_disagreements: tuple[Mapping[str, object], ...]
    gap_distribution: Mapping[str, int]
    pareto_frontier: tuple[Mapping[str, object], ...]
    methodology: str
    auto_switch: Literal[False] = False

    @model_validator(mode="after")
    def _grade_cap_invariant(self) -> EvalRecommendation:
        """RELIABLE only off an outcome_label / human_labeled rung (§8.2)."""
        if self.grade is EvalGrade.RELIABLE and self.label_source not in _RELIABLE_LABEL_SOURCES:
            raise ValueError(
                "a RELIABLE grade requires label_source in "
                "{outcome_label, human_labeled}; judge/reference cap at directional (§8.2)"
            )
        return self


__all__ = [
    "CostEstimate",
    "CostGatePhase",
    "EvalCase",
    "EvalDataset",
    "EvalRecommendation",
    "ModelCandidate",
    "ProviderKeyRef",
]
