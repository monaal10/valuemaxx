"""SEARCH — prune to a few candidates, then successive halving (§8.4).

Not 100 models: $0 priors prune to ~3-8, then **successive halving**:

1. **smoke** (n in [30, 50]): drop every candidate that underperforms the incumbent
   by **> 25%** — strictly, with **NO confidence-interval requirement** at this
   stage (n is too small to separate CIs for small deltas). Cap survivors at the
   top 3 by parity.
2. **confirmation** (n in [200, 500]): escalate the survivors; a candidate is the
   winner only when its parity is >= the incumbent AND its 95% CI **separates** from
   the incumbent's (the CI requirement applies only here). Among separated winners,
   the lowest-cost one wins.

OSS candidates are costed **fully-loaded** (GPU + ops / real volume) — "free per
token" is often the most expensive point at low volume, so the per-call cost is the
whole infra bill divided by calls, never zero. The result feeds a cost x quality x
latency Pareto frontier with dominated points flagged.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from valuemaxx.eval.stats import ci_separated, underperforms_by, wilson_ci

if TYPE_CHECKING:
    from collections.abc import Sequence

_SMOKE_MIN, _SMOKE_MAX = 30, 50
_CONFIRM_MIN, _CONFIRM_MAX = 200, 500
_SMOKE_DROP_FRACTION = 0.25
_MAX_SMOKE_SURVIVORS = 3


@dataclass(frozen=True, slots=True)
class CandidateScore:
    """One candidate's measured score on an eval stage (frozen, eval-local).

    ``passes``/``n`` give the parity proportion; ``cost_usd`` and ``latency_ms_p50``
    are the other two Pareto axes. OSS candidates carry a fully-loaded ``cost_usd``.
    """

    model: str
    passes: int
    n: int
    cost_usd: float
    latency_ms_p50: float

    @property
    def parity(self) -> float:
        """The parity proportion ``passes / n`` (0.0 for an empty run)."""
        return self.passes / self.n if self.n else 0.0


@dataclass(frozen=True, slots=True)
class ParetoPoint:
    """A candidate's position on the cost x quality x latency frontier (§8.4)."""

    model: str
    quality: float
    cost_usd: float
    latency_ms_p50: float
    dominated: bool


def smoke_eval(
    *, incumbent: CandidateScore, candidates: Sequence[CandidateScore]
) -> tuple[CandidateScore, ...]:
    """Run the smoke stage: drop >25% underperformers (NO CI), keep the top 3 (§8.4).

    Every candidate (and the incumbent) must have run on 30-50 cases. Survivors are
    those NOT underperforming the incumbent's parity by more than 25% (strict ``<``),
    capped at the 3 highest-parity. There is deliberately no CI requirement here.

    Raises:
        ValueError: if any run's ``n`` is outside the smoke range [30, 50].
    """
    for score in (incumbent, *candidates):
        if not _SMOKE_MIN <= score.n <= _SMOKE_MAX:
            raise ValueError(
                f"smoke eval runs on {_SMOKE_MIN}-{_SMOKE_MAX} cases; {score.model!r} "
                f"has n={score.n}"
            )
    survivors = [
        c
        for c in candidates
        if not underperforms_by(
            candidate=c.parity, incumbent=incumbent.parity, fraction=_SMOKE_DROP_FRACTION
        )
    ]
    # Successive halving: keep the top 3 by parity (then cost as a stable tiebreak).
    survivors.sort(key=lambda c: (-c.parity, c.cost_usd, c.model))
    return tuple(survivors[:_MAX_SMOKE_SURVIVORS])


def confirmation_eval(
    *, incumbent: CandidateScore, survivors: Sequence[CandidateScore]
) -> tuple[CandidateScore, ...]:
    """Run the confirmation stage on 200-500 cases; return the confirmed scores (§8.4).

    Raises:
        ValueError: if any run's ``n`` is outside the confirmation range [200, 500].
    """
    for score in (incumbent, *survivors):
        if not _CONFIRM_MIN <= score.n <= _CONFIRM_MAX:
            raise ValueError(
                f"confirmation eval runs on {_CONFIRM_MIN}-{_CONFIRM_MAX} cases; "
                f"{score.model!r} has n={score.n}"
            )
    return tuple(survivors)


def pick_winner(
    *, incumbent: CandidateScore, confirmed: Sequence[CandidateScore]
) -> CandidateScore | None:
    """Pick the winner: parity >= incumbent AND 95% CI separates; lowest-cost wins (§8.4).

    A candidate wins only when its parity is at least the incumbent's AND its 95%
    Wilson CI is strictly disjoint from the incumbent's (the CI requirement applies
    here, not at smoke). Among all candidates that clear both gates, the lowest-cost
    one is recommended. Returns ``None`` when nothing separates — never a guess.
    """
    incumbent_ci = wilson_ci(successes=incumbent.passes, n=incumbent.n)
    qualifying = [
        c
        for c in confirmed
        if c.parity >= incumbent.parity
        and ci_separated(wilson_ci(successes=c.passes, n=c.n), incumbent_ci)
    ]
    if not qualifying:
        return None
    return min(qualifying, key=lambda c: (c.cost_usd, c.model))


def pareto_frontier(scores: Sequence[CandidateScore]) -> tuple[ParetoPoint, ...]:
    """Build the cost x quality x latency frontier, flagging dominated points (§8.4).

    A point is ``dominated`` when another point is at least as good on all three axes
    (higher-or-equal quality, lower-or-equal cost, lower-or-equal latency) and
    strictly better on at least one. Dominated points are flagged, not dropped, so
    the report can show the full frontier.
    """
    points: list[ParetoPoint] = []
    for candidate in scores:
        dominated = any(_dominates(other, candidate) for other in scores if other is not candidate)
        points.append(
            ParetoPoint(
                model=candidate.model,
                quality=candidate.parity,
                cost_usd=candidate.cost_usd,
                latency_ms_p50=candidate.latency_ms_p50,
                dominated=dominated,
            )
        )
    return tuple(points)


def _dominates(a: CandidateScore, b: CandidateScore) -> bool:
    """Whether ``a`` Pareto-dominates ``b`` (>= on all axes, strictly > on one)."""
    at_least_as_good = (
        a.parity >= b.parity
        and a.cost_usd <= b.cost_usd
        and a.latency_ms_p50 <= b.latency_ms_p50
    )
    strictly_better = (
        a.parity > b.parity or a.cost_usd < b.cost_usd or a.latency_ms_p50 < b.latency_ms_p50
    )
    return at_least_as_good and strictly_better


def fully_loaded_oss_cost(*, monthly_infra_usd: float, monthly_calls: int) -> float:
    """Fully-loaded per-call cost of an OSS model: infra / volume (§8.4).

    "Free per token" is a trap at low volume: the per-call cost is the whole monthly
    infra bill (GPU + ops) divided by the call volume. At zero volume the per-call
    cost is the entire bill, never zero — that is exactly the point §8.4 makes.
    """
    if monthly_calls <= 0:
        return monthly_infra_usd
    return monthly_infra_usd / monthly_calls


__all__ = [
    "CandidateScore",
    "ParetoPoint",
    "confirmation_eval",
    "fully_loaded_oss_cost",
    "pareto_frontier",
    "pick_winner",
    "smoke_eval",
]
