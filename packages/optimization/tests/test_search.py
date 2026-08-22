from __future__ import annotations

from decimal import Decimal

from valuemaxx.core.optimization import OptimizationConfig
from valuemaxx.optimization.search import SearchCandidate, prefilter_by_cost, successive_halving


def _candidate(name: str, cost: str) -> SearchCandidate:
    return SearchCandidate(
        config=OptimizationConfig(model=name, provider="p"), estimated_cost=Decimal(cost)
    )


def test_cost_prefilter_never_evaluates_candidates_without_meaningful_savings() -> None:
    kept = prefilter_by_cost(
        incumbent_cost=Decimal("1.00"),
        candidates=(_candidate("cheap", "0.80"), _candidate("noise", "0.97")),
        minimum_savings=Decimal("0.05"),
    )
    assert [c.config.model for c in kept] == ["cheap"]


def test_successive_halving_uses_50_200_1000_and_keeps_ceil_half() -> None:
    candidates = tuple(_candidate(str(i), f"0.{i + 1}") for i in range(7))
    calls: list[tuple[int, tuple[str, ...]]] = []

    def evaluate(stage: int, active: tuple[SearchCandidate, ...]) -> dict[str, float]:
        calls.append((stage, tuple(c.config.model for c in active)))
        return {c.identity: float(c.config.model) for c in active}

    result = successive_halving(candidates, evaluate=evaluate)
    assert [stage for stage, _ in calls] == [50, 200, 1000]
    assert [len(active) for _, active in calls] == [7, 4, 2]
    assert [c.config.model for c in result.survivors] == ["6"]
    assert [r.sample_size for r in result.rounds] == [50, 200, 1000]


def test_ties_are_deterministic_and_prefer_lower_cost() -> None:
    candidates = (_candidate("b", "0.4"), _candidate("a", "0.3"))
    result = successive_halving(
        candidates, evaluate=lambda _stage, active: {c.identity: 1.0 for c in active}
    )
    assert result.survivors[0].config.model == "a"
