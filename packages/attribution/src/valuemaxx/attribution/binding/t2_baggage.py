"""T2 baggage resolver — ``exact``, run_id rides W3C baggage across hops (§6.3).

When a run spans live service hops, the SDK propagates the ``run_id`` on W3C
baggage; the cascade reads the inbound baggage into
:attr:`~valuemaxx.attribution.resolver.ResolveContext.baggage` (a plain string
map, so this logic package never hard-depends on an OTel runtime). T2 reads the
well-known baggage key. Absent or blank => no match (never invents a run id).
"""

from __future__ import annotations

from typing_extensions import override
from valuemaxx.attribution.resolver import ResolveContext, ResolveOutcome, Resolver, no_match
from valuemaxx.core import BindingTier, RunId
from valuemaxx.core.wire import BAGGAGE_RUN_ID_KEY

# BAGGAGE_RUN_ID_KEY is re-exported from the cross-language wire contract
# (:mod:`valuemaxx.core.wire`) so the T2 producer and this consumer read one constant.


class BaggageResolver(Resolver):
    """T2: bind the outcome to the ``run_id`` carried on W3C baggage (exact)."""

    tier = BindingTier.EXACT

    @override
    def _resolve(self, ctx: ResolveContext) -> ResolveOutcome:
        raw = ctx.baggage.get(BAGGAGE_RUN_ID_KEY)
        if raw is None or not raw.strip():
            return no_match()
        return self.matched_outcome(
            [
                self.candidate(
                    run_id=RunId(raw),
                    score=1.0,
                    rationale="W3C baggage run_id",
                )
            ]
        )


__all__ = ["BAGGAGE_RUN_ID_KEY", "BaggageResolver"]
