"""Cost prefilter and generic, deterministic successive halving."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from valuemaxx.core.optimization import OptimizationConfig

STAGES: tuple[int, ...] = (50, 200, 1000)


@dataclass(frozen=True, slots=True)
class SearchCandidate:
    """A discrete configuration and its pre-replay expected cost."""

    config: OptimizationConfig
    estimated_cost: Decimal

    @property
    def identity(self) -> str:
        return hashlib.sha256(self.config.model_dump_json().encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class HalvingRound:
    """One stage's complete ranking and retained half."""

    sample_size: int
    evaluated: tuple[SearchCandidate, ...]
    survivors: tuple[SearchCandidate, ...]
    scores: tuple[tuple[str, float], ...]


@dataclass(frozen=True, slots=True)
class HalvingResult:
    """Trace of the search; keeping the trace makes elimination auditable."""

    survivors: tuple[SearchCandidate, ...]
    rounds: tuple[HalvingRound, ...]


StageEvaluator = Callable[[int, tuple[SearchCandidate, ...]], Mapping[str, float]]


def prefilter_by_cost(
    *,
    incumbent_cost: Decimal,
    candidates: Sequence[SearchCandidate],
    minimum_savings: Decimal = Decimal("0.05"),
) -> tuple[SearchCandidate, ...]:
    """Keep only configurations meaningfully cheaper than the incumbent."""
    if incumbent_cost < 0:
        raise ValueError("incumbent_cost cannot be negative")
    if not Decimal(0) <= minimum_savings <= Decimal(1):
        raise ValueError("minimum_savings must be between 0 and 1")
    ceiling = incumbent_cost * (Decimal(1) - minimum_savings)
    return tuple(candidate for candidate in candidates if candidate.estimated_cost <= ceiling)


def successive_halving(
    candidates: Sequence[SearchCandidate],
    *,
    evaluate: StageEvaluator,
    stages: tuple[int, ...] = STAGES,
) -> HalvingResult:
    """Evaluate at 50/200/1000 examples, retaining the top ceil-half each time."""
    if stages != STAGES:
        raise ValueError("optimization stages must be exactly 50, 200, 1000")
    active = tuple(candidates)
    rounds: list[HalvingRound] = []
    for sample_size in stages:
        if not active:
            break
        scores = evaluate(sample_size, active)
        missing = [candidate.identity for candidate in active if candidate.identity not in scores]
        if missing:
            raise ValueError(f"evaluator omitted {len(missing)} candidate score(s)")
        ranked = tuple(
            sorted(
                active,
                key=lambda candidate: (
                    -scores[candidate.identity],
                    candidate.estimated_cost,
                    candidate.identity,
                ),
            )
        )
        survivors = ranked[: math.ceil(len(ranked) / 2)]
        rounds.append(
            HalvingRound(
                sample_size=sample_size,
                evaluated=active,
                survivors=survivors,
                scores=tuple(
                    (candidate.identity, scores[candidate.identity]) for candidate in ranked
                ),
            )
        )
        active = survivors
    return HalvingResult(survivors=active, rounds=tuple(rounds))


__all__ = [
    "STAGES",
    "HalvingResult",
    "HalvingRound",
    "SearchCandidate",
    "StageEvaluator",
    "prefilter_by_cost",
    "successive_halving",
]
