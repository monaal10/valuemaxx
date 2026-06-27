"""valuemaxx.attribution — the binding cascade (T1->T5), exact-first, inference-last.

The cascade binds each :class:`~valuemaxx.core.OutcomeEvent` to the run that
produced it, labeling every binding with its system-owned
:class:`~valuemaxx.core.BindingTier` (§6.3). Deterministic tiers (T1 ambient
context, T2 W3C baggage, T3 round-trip id) short-circuit to a billing-grade
result; the inferred tiers (T4 entity-match -> ``candidate``, T5 semantic ->
``likely``) are always review-queued and never fed to billing-grade metrics.

Depends only on ``valuemaxx.core`` ABCs/Protocols and ``valuemaxx.capabilities``;
it never imports a sibling logic package or ``valuemaxx.store``.
"""

from __future__ import annotations

from valuemaxx.attribution.capabilities import (
    AttributionNotWiredError,
    AttributionRuntime,
    bind_runtime,
    register,
)
from valuemaxx.attribution.cascade import Cascade
from valuemaxx.attribution.confidence import label_for
from valuemaxx.attribution.resolver import (
    ResolveContext,
    ResolveOutcome,
    Resolver,
    no_match,
)

__all__ = [
    "AttributionNotWiredError",
    "AttributionRuntime",
    "Cascade",
    "ResolveContext",
    "ResolveOutcome",
    "Resolver",
    "bind_runtime",
    "label_for",
    "no_match",
    "register",
]
