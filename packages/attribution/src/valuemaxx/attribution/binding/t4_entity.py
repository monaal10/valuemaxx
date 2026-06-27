"""T4 entity-match resolver — ``candidate``; the T3-echo Phase-1 fallback (§6.3).

When T3's round-trip echo is absent (the external system does not echo metadata),
an outcome can still be tied to a run via a shared durable entity id
(``customer_id``/``order_id``). T4 queries
:meth:`~valuemaxx.core.RunRepository.list_by_entity` (tenant-scoped) for each of
the outcome's entity keys, keeps runs whose start falls within ``±window`` of the
outcome time, and tie-breaks by time proximity (closer => higher score).

This is an *advisory* tier: it produces only the ``candidate`` tier and is always
review-queued by the cascade — it never promotes to ``deterministic``. When the
two closest runs are indistinguishably close (their time-distances differ by less
than ``epsilon``), the outcome is flagged ``ambiguous`` so the cascade halts it to
human review rather than guessing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from typing_extensions import override
from valuemaxx.attribution.resolver import ResolveContext, ResolveOutcome, Resolver, no_match
from valuemaxx.core import BindingTier

if TYPE_CHECKING:
    from datetime import timedelta

    from valuemaxx.core import Run, RunRepository

_DEFAULT_EPSILON_SECONDS = 1.0


class EntityMatchResolver(Resolver):
    """T4: bind via a shared entity id within a time window (candidate tier)."""

    tier = BindingTier.CANDIDATE

    def __init__(
        self,
        *,
        run_repo: RunRepository,
        window: timedelta,
        epsilon: timedelta | None = None,
    ) -> None:
        """Configure the resolver.

        Args:
            run_repo: the tenant-scoped run repository to query by entity key.
            window: the symmetric ``±window`` around the outcome time a run must
                start within to be considered.
            epsilon: the minimum time-distance gap between the two closest runs
                below which the match is treated as ambiguous (defaults to 1s).
        """
        self._run_repo = run_repo
        self._window = window
        self._epsilon_seconds = (
            epsilon.total_seconds() if epsilon is not None else _DEFAULT_EPSILON_SECONDS
        )

    @override
    def _resolve(self, ctx: ResolveContext) -> ResolveOutcome:
        runs = self._matching_runs(ctx)
        if not runs:
            return no_match()

        window_seconds = self._window.total_seconds()
        scored: list[tuple[Run, float, float]] = []  # (run, distance_seconds, score)
        for run in runs:
            distance = abs((run.started_at - ctx.occurred_at).total_seconds())
            # Linear proximity score in (0, 1]: 1.0 at the exact instant, ->0 at the
            # window edge. window_seconds > 0 by construction (a positive timedelta).
            score = 1.0 - (distance / window_seconds)
            scored.append((run, distance, score))

        scored.sort(key=lambda item: item[1])  # closest first
        ambiguous = self._is_ambiguous(scored)
        candidates = tuple(
            self.candidate(
                run_id=run.id,
                score=score,
                rationale=f"entity-match within ±{self._window} (Δ={distance:.0f}s)",
            )
            for run, distance, score in scored
        )
        return self.matched_outcome(candidates, ambiguous=ambiguous)

    def _matching_runs(self, ctx: ResolveContext) -> list[Run]:
        """The in-window, de-duplicated runs sharing any of the outcome's entity keys."""
        seen: dict[str, Run] = {}
        for entity_key in ctx.entity_keys:
            for run in self._run_repo.list_by_entity(ctx.tenant_id, entity_key):
                if self._within_window(run, ctx) and run.id not in seen:
                    seen[run.id] = run
        return list(seen.values())

    def _within_window(self, run: Run, ctx: ResolveContext) -> bool:
        distance = abs((run.started_at - ctx.occurred_at).total_seconds())
        return distance <= self._window.total_seconds()

    def _is_ambiguous(self, scored: list[tuple[Run, float, float]]) -> bool:
        """True iff the two closest runs are within ``epsilon`` of each other in time."""
        if len(scored) < 2:
            return False
        closest, second = scored[0][1], scored[1][1]
        return abs(closest - second) < self._epsilon_seconds


__all__ = ["EntityMatchResolver"]
