from __future__ import annotations

from decimal import Decimal

from valuemaxx.core.optimization import (
    CandidateMetrics,
    CandidateStatus,
    EvidenceTier,
    OptimizationConfig,
    OptimizationConstraints,
)
from valuemaxx.optimization.frontier import FrontierCandidate, build_frontier, evaluate_constraints


def _metrics(**changes: object) -> CandidateMetrics:
    values: dict[str, object] = {
        "cost_per_unit": Decimal("0.05"),
        "outcome_rate": Decimal("0.08"),
        "error_rate": Decimal("0.01"),
        "refusal_rate": Decimal("0.01"),
        "p95_latency_ms": 1000,
        "sample_size": 1000,
    }
    values.update(changes)
    return CandidateMetrics(**values)  # type: ignore[arg-type]


CONSTRAINTS = OptimizationConstraints(
    outcome_margin=Decimal("0.01"), max_latency_factor=Decimal("1.2")
)
BASELINE = _metrics(cost_per_unit=Decimal("0.10"), outcome_rate=Decimal("0.08"))


def test_constraints_are_separate_from_cost_objective() -> None:
    verdict = evaluate_constraints(
        baseline=BASELINE,
        candidate=_metrics(outcome_rate=Decimal("0.06"), p95_latency_ms=1300),
        constraints=CONSTRAINTS,
    )
    assert set(verdict.failed) == {"outcome_rate", "p95_latency"}
    assert verdict.passed is False


def test_missing_outcome_is_pending_not_a_false_failure() -> None:
    verdict = evaluate_constraints(
        baseline=BASELINE,
        candidate=_metrics(outcome_rate=None),
        constraints=CONSTRAINTS,
    )
    assert verdict.failed == ()
    assert verdict.pending == ("outcome_rate",)
    assert verdict.passed is None


def test_frontier_keeps_replay_only_rows_and_marks_status_honestly() -> None:
    config = OptimizationConfig(model="cheap", provider="p")
    entries = build_frontier(
        baseline=BASELINE,
        constraints=CONSTRAINTS,
        candidates=(
            FrontierCandidate(
                config=config,
                metrics=_metrics(outcome_rate=None),
                evidence_tier=EvidenceTier.REPLAY,
            ),
        ),
    )
    assert entries[0].status is CandidateStatus.EVALUATING
    assert entries[0].failed_constraints == ()


def test_failed_candidate_is_retained_on_frontier() -> None:
    entries = build_frontier(
        baseline=BASELINE,
        constraints=CONSTRAINTS,
        candidates=(
            FrontierCandidate(
                config=OptimizationConfig(model="bad", provider="p"),
                metrics=_metrics(error_rate=Decimal("0.02")),
                evidence_tier=EvidenceTier.LIVE_GUARDRAILS,
            ),
        ),
    )
    assert entries[0].status is CandidateStatus.FAILED
    assert entries[0].failed_constraints == ("error_rate",)
