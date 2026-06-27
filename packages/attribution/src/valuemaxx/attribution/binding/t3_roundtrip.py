"""T3 round-trip-id resolver — ``deterministic``, echoed run_id (§6.3, H4).

The technical heart of delayed attribution: the agent stamps a durable ``run_id``
into an outbound external object (Stripe metadata, ticket custom field); the later
webhook **echoes it back**, and the outcomes package surfaces it on
:attr:`~valuemaxx.attribution.resolver.ResolveContext.echoed_run_id`. T3 converts
"impossible delayed attribution" into a deterministic join.

Works only where the external system echoes arbitrary metadata. When the echo is
absent (e.g. Salesforce outbound messages don't echo), T3 returns ``matched=False``
and the outcome falls through to T4 entity-match (labeled), never mis-bound.
"""

from __future__ import annotations

from typing_extensions import override
from valuemaxx.attribution.resolver import ResolveContext, ResolveOutcome, Resolver, no_match
from valuemaxx.core import BindingTier


class RoundTripResolver(Resolver):
    """T3: bind the outcome to the round-tripped (echoed) ``run_id`` (deterministic)."""

    tier = BindingTier.DETERMINISTIC

    @override
    def _resolve(self, ctx: ResolveContext) -> ResolveOutcome:
        if ctx.echoed_run_id is None:
            return no_match()
        return self.matched_outcome(
            [
                self.candidate(
                    run_id=ctx.echoed_run_id,
                    score=1.0,
                    rationale="round-tripped run_id echoed in outcome metadata",
                )
            ]
        )


__all__ = ["RoundTripResolver"]
