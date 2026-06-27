"""The binding cascade orchestrator (ATTR-4) — exact-first, inference-last (§6.3).

:meth:`Cascade.bind` walks the resolvers in tier order (T1 ambient -> T2 baggage
-> T3 round-trip -> T4 entity -> T5 semantic), first match wins, and labels every
result with its system-owned :class:`~valuemaxx.core.BindingTier`:

- A **deterministic** match (T1/T2/T3 -> exact/deterministic) short-circuits to a
  billing-grade :class:`~valuemaxx.core.AttributionResult` with
  ``review_required=False`` — but only after **fast-path revalidation** confirms
  the run still exists in the repository. A dangling run id is refused (downgraded)
  and the cascade falls through; we never bind a ghost run.
- **T4 candidate** is advisory: ``review_required=True``, enqueued, never
  billing-grade. An epsilon-tie HALTS — the result is left unbound (no single run)
  with all tied candidates enqueued for human disambiguation.
- **T5 likely** is the labeled last resort: ``review_required=True``, enqueued,
  never billing-grade.
- **No match** yields an unbound, review-required result, also enqueued.

The cascade depends only on ``valuemaxx.core`` ABCs/Protocols (``RunRepository``,
``ReviewQueue``, ``LlmJudge``) — never a sibling logic package or ``valuemaxx.store``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from valuemaxx.attribution.binding.t1_ambient import AmbientContextResolver
from valuemaxx.attribution.binding.t2_baggage import BAGGAGE_RUN_ID_KEY, BaggageResolver
from valuemaxx.attribution.binding.t3_roundtrip import RoundTripResolver
from valuemaxx.attribution.binding.t4_entity import EntityMatchResolver
from valuemaxx.attribution.inference.t5_semantic import SemanticInferenceResolver
from valuemaxx.attribution.resolver import ResolveContext, ResolveOutcome, Resolver
from valuemaxx.core import AttributionResult

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from datetime import timedelta

    from valuemaxx.core import (
        AttributionCandidate,
        LlmJudge,
        OutcomeEvent,
        ReviewQueue,
        RunId,
        RunRepository,
    )

class Cascade:
    """Walks the binding resolvers in tier order and produces a labeled result."""

    def __init__(
        self,
        *,
        run_repo: RunRepository,
        review_queue: ReviewQueue,
        judge: LlmJudge | None = None,
        entity_window: timedelta,
        semantic_window: timedelta | None = None,
    ) -> None:
        """Configure the cascade with its core ABC/Protocol dependencies.

        Args:
            run_repo: tenant-scoped run repository (entity lookups + fast-path
                revalidation of deterministic run ids).
            review_queue: where candidate/likely/unbound results are enqueued.
            judge: injected LLM-judge for T5 (deterministic under test); ``None``
                disables the semantic tier.
            entity_window: the ±window for T4 entity-match.
            semantic_window: the ±window for T5 (defaults to ``entity_window``).
        """
        self._run_repo = run_repo
        self._review_queue = review_queue
        self._deterministic: tuple[Resolver, ...] = (
            AmbientContextResolver(),
            BaggageResolver(),
            RoundTripResolver(),
        )
        self._entity = EntityMatchResolver(run_repo=run_repo, window=entity_window)
        self._semantic = SemanticInferenceResolver(
            run_repo=run_repo,
            judge=judge,
            window=semantic_window if semantic_window is not None else entity_window,
        )

    def bind(
        self,
        outcome: OutcomeEvent,
        *,
        ambient_run_id: RunId | None = None,
        baggage: Mapping[str, str] | None = None,
        echoed_run_id: RunId | None = None,
    ) -> AttributionResult:
        """Bind ``outcome`` to its run, labeling the result with its tier.

        The deterministic signals (ambient run id, baggage, echoed run id) are
        supplied by the caller (the SDK/outcomes ingest path) since they ride
        transport context the cascade cannot read itself.
        """
        ctx = self._context(outcome, ambient_run_id, baggage, echoed_run_id)

        deterministic = self._bind_deterministic(ctx)
        if deterministic is not None:
            return deterministic

        return self._bind_advisory(ctx)

    # --- deterministic tiers (short-circuit + fast-path revalidation) ------------

    def _bind_deterministic(self, ctx: ResolveContext) -> AttributionResult | None:
        """Try T1/T2/T3; return a billing-grade result, or None to fall through.

        Each deterministic match is **revalidated** against the repository — a run
        id that no longer exists is refused (downgraded), and the cascade continues
        to the next tier rather than binding a ghost.
        """
        for resolver in self._deterministic:
            outcome = resolver.resolve(ctx)
            if not outcome.matched:
                continue
            candidate = outcome.candidates[0]
            if self._run_repo.get(ctx.tenant_id, candidate.run_id) is None:
                continue  # dangling run id => downgrade, never bind a ghost
            return AttributionResult(
                tenant_id=ctx.tenant_id,
                outcome_id=ctx.outcome_id,
                run_id=candidate.run_id,
                tier=candidate.tier,
                bound_by=type(resolver).__name__,
                candidates=outcome.candidates,
                review_required=False,
            )
        return None

    # --- advisory tiers (always review-required, never billing-grade) -----------

    def _bind_advisory(self, ctx: ResolveContext) -> AttributionResult:
        """Try T4 then T5; otherwise an unbound result. Always review-required."""
        entity = self._entity.resolve(ctx)
        if entity.matched:
            return self._enqueue(self._advisory_result(ctx, self._entity, entity))

        semantic = self._semantic.resolve(ctx)
        if semantic.matched:
            return self._enqueue(self._advisory_result(ctx, self._semantic, semantic))

        return self._enqueue(self._unbound_result(ctx))

    def _advisory_result(
        self, ctx: ResolveContext, resolver: Resolver, outcome: ResolveOutcome
    ) -> AttributionResult:
        """Build a review-required result from an advisory (candidate/likely) match.

        An ``ambiguous`` outcome is HALTED: no single run is bound (``run_id`` /
        ``tier`` are None) but every tied candidate is carried for human review.
        Otherwise the top-scored candidate is bound advisorily.
        """
        if outcome.ambiguous:
            return AttributionResult(
                tenant_id=ctx.tenant_id,
                outcome_id=ctx.outcome_id,
                run_id=None,
                tier=None,
                bound_by=type(resolver).__name__,
                candidates=outcome.candidates,
                review_required=True,
            )
        top = self._top_candidate(outcome.candidates)
        return AttributionResult(
            tenant_id=ctx.tenant_id,
            outcome_id=ctx.outcome_id,
            run_id=top.run_id,
            tier=top.tier,
            bound_by=type(resolver).__name__,
            candidates=outcome.candidates,
            review_required=True,
        )

    def _unbound_result(self, ctx: ResolveContext) -> AttributionResult:
        """An unbound, review-required result (no tier matched)."""
        return AttributionResult(
            tenant_id=ctx.tenant_id,
            outcome_id=ctx.outcome_id,
            run_id=None,
            tier=None,
            bound_by=None,
            candidates=(),
            review_required=True,
        )

    def _enqueue(self, result: AttributionResult) -> AttributionResult:
        """Enqueue a review-required result onto the tenant-scoped review queue."""
        self._review_queue.enqueue(result.tenant_id, result)
        return result

    # --- helpers ----------------------------------------------------------------

    @staticmethod
    def _top_candidate(candidates: Sequence[AttributionCandidate]) -> AttributionCandidate:
        """The highest-scored candidate (ties broken arbitrarily but deterministically)."""
        return max(candidates, key=lambda c: c.score)

    def _context(
        self,
        outcome: OutcomeEvent,
        ambient_run_id: RunId | None,
        baggage: Mapping[str, str] | None,
        echoed_run_id: RunId | None,
    ) -> ResolveContext:
        """Build the resolve context from the outcome + caller-supplied signals."""
        content = outcome.raw.get("content")
        return ResolveContext(
            tenant_id=outcome.tenant_id,
            outcome_id=outcome.id,
            occurred_at=outcome.occurred_at,
            entity_keys=outcome.entity_keys,
            ambient_run_id=ambient_run_id,
            baggage=baggage if baggage is not None else {},
            echoed_run_id=echoed_run_id,
            content=content if isinstance(content, str) else "",
        )


__all__ = ["BAGGAGE_RUN_ID_KEY", "Cascade"]
