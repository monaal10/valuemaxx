"""OutcomeEvent + OutcomeBinding — the signal-classed outcome record (§6.2).

``OutcomeBinding`` holds the run link and its tier; all three fields are nullable
until the outcome is bound by the attribution cascade. ``OutcomeEvent`` carries
the required ``signal_class`` honesty axis and a dedup key that prefers the
round-tripped ``correlation_id`` (T3) and falls back to ``(source, id)``.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal

from atm_core.base import StrictModel, TenantScopedModel
from atm_core.enums import BindingTier, SignalClass
from atm_core.ids import CorrelationId, OutcomeEventId, RunId


class OutcomeBinding(StrictModel):
    """The (possibly unbound) link from an outcome to the run that produced it."""

    run_id: RunId | None
    tier: BindingTier | None
    bound_by: str | None


class OutcomeEvent(TenantScopedModel):
    """A declared business outcome, signal-classed and (eventually) bound to a run."""

    id: OutcomeEventId
    name: str
    signal_class: SignalClass
    value: Decimal | None
    occurred_at: datetime
    binding: OutcomeBinding
    entity_keys: frozenset[tuple[str, str]]
    correlation_id: CorrelationId | None
    source: str
    raw: Mapping[str, object]

    @property
    def idempotency_key(self) -> CorrelationId | tuple[str, OutcomeEventId]:
        """Dedup key: the round-tripped correlation_id if present, else (source, id)."""
        if self.correlation_id is not None:
            return self.correlation_id
        return (self.source, self.id)


__all__ = ["OutcomeBinding", "OutcomeEvent"]
