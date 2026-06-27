"""T1 ambient-context resolver — ``exact``, only when context propagated (§6.3).

The active ``run_id`` rides a :class:`~contextvars.ContextVar`. ``asyncio`` tasks
propagate it; raw ``ThreadPoolExecutor.submit`` and ``os.fork``/multiprocessing do
NOT (PEP 567, H10). The cascade snapshots the ambient id onto the
:class:`~valuemaxx.attribution.resolver.ResolveContext` at capture time; this
resolver prefers that snapshot and falls back to the live core contextvar.

When neither is set — the context did not propagate to where the outcome fired —
this resolver returns ``matched=False`` and the cascade falls through to a lower
tier (labeled), **never** silently mis-binding to a guessed run.
"""

from __future__ import annotations

from typing_extensions import override
from valuemaxx.attribution.resolver import ResolveContext, ResolveOutcome, Resolver, no_match
from valuemaxx.core import BindingTier, active_run_id


class AmbientContextResolver(Resolver):
    """T1: bind the outcome to the ambient ``run_id`` (exact) when context propagated."""

    tier = BindingTier.EXACT

    @override
    def _resolve(self, ctx: ResolveContext) -> ResolveOutcome:
        run_id = ctx.ambient_run_id if ctx.ambient_run_id is not None else active_run_id.get()
        if run_id is None:
            return no_match()
        return self.matched_outcome(
            [self.candidate(run_id=run_id, score=1.0, rationale="ambient contextvar run_id")]
        )


__all__ = ["AmbientContextResolver"]
