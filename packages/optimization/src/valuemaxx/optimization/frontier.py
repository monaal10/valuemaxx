"""Constraint evaluation and honest frontier construction."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from valuemaxx.core.optimization import CandidateStatus, FrontierEntry

if TYPE_CHECKING:
    from collections.abc import Sequence

    from valuemaxx.core.optimization import (
        CandidateMetrics,
        EvidenceTier,
        OptimizationConfig,
        OptimizationConstraints,
    )


@dataclass(frozen=True, slots=True)
class ConstraintVerdict:
    """Tri-state constraint result: pass, fail, or pending delayed evidence."""

    passed: bool | None
    failed: tuple[str, ...]
    pending: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FrontierCandidate:
    config: OptimizationConfig
    metrics: CandidateMetrics
    evidence_tier: EvidenceTier


def evaluate_constraints(
    *,
    baseline: CandidateMetrics,
    candidate: CandidateMetrics,
    constraints: OptimizationConstraints,
) -> ConstraintVerdict:
    """Evaluate business constraints without mixing cost into the verdict."""
    failed: list[str] = []
    pending: list[str] = []
    if baseline.outcome_rate is None or candidate.outcome_rate is None:
        pending.append("outcome_rate")
    elif candidate.outcome_rate < baseline.outcome_rate - constraints.outcome_margin:
        failed.append("outcome_rate")
    if not constraints.error_rate_may_increase and candidate.error_rate > baseline.error_rate:
        failed.append("error_rate")
    if not constraints.refusal_rate_may_increase and candidate.refusal_rate > baseline.refusal_rate:
        failed.append("refusal_rate")
    latency_limit = Decimal(baseline.p95_latency_ms) * constraints.max_latency_factor
    if Decimal(candidate.p95_latency_ms) > latency_limit:
        failed.append("p95_latency")
    passed: bool | None = False if failed else (None if pending else True)
    return ConstraintVerdict(passed=passed, failed=tuple(failed), pending=tuple(pending))


def build_frontier(
    *,
    baseline: CandidateMetrics,
    constraints: OptimizationConstraints,
    candidates: Sequence[FrontierCandidate],
) -> tuple[FrontierEntry, ...]:
    """Keep every candidate row, ordered by objective, with honest constraint state."""
    entries: list[FrontierEntry] = []
    for candidate in candidates:
        verdict = evaluate_constraints(
            baseline=baseline, candidate=candidate.metrics, constraints=constraints
        )
        status = (
            CandidateStatus.PASSED
            if verdict.passed is True
            else CandidateStatus.FAILED
            if verdict.passed is False
            else CandidateStatus.EVALUATING
        )
        entries.append(
            FrontierEntry(
                config=candidate.config,
                metrics=candidate.metrics,
                evidence_tier=candidate.evidence_tier,
                status=status,
                failed_constraints=verdict.failed,
            )
        )
    return tuple(
        sorted(entries, key=lambda entry: (entry.metrics.cost_per_unit, entry.config.model))
    )


__all__ = [
    "ConstraintVerdict",
    "FrontierCandidate",
    "build_frontier",
    "evaluate_constraints",
]
