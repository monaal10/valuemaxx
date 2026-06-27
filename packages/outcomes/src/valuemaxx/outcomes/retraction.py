"""OUT-E: outcome retraction (``outcome_confirmed`` -> ``outcome_retracted``, H8).

A confirmed business outcome can later prove false — a "resolved" ticket reopens, a
payment is refunded. :func:`retract_outcome` flips **only** a confirmed outcome to
``outcome_retracted`` (the status guard); an ``action_attempted`` outcome is never
retracted, and re-retracting an already-retracted outcome is an idempotent no-op. The
retraction is what removes the outcome from the cost-per-outcome *denominator*
downstream (G2-METRICS) and triggers the correction notice (G4-NOTIFY); this function
owns the state flip only.

The flip is delegated to the repository's append-style ``retract`` (which replaces the
stored record with a retracted copy), so this module stays storage-agnostic — it depends
only on the :class:`~valuemaxx.core.OutcomeEventRepository` ABC.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from valuemaxx.core import SignalClass

if TYPE_CHECKING:
    from valuemaxx.core import OutcomeEventId, OutcomeEventRepository, TenantId


class RetractionResult(Enum):
    """The outcome of a retraction attempt (so callers can report precisely)."""

    RETRACTED = "retracted"
    ALREADY_RETRACTED = "already_retracted"
    NOT_CONFIRMED = "not_confirmed"
    NOT_FOUND = "not_found"


def retract_outcome(
    repository: OutcomeEventRepository,
    *,
    tenant_id: TenantId,
    outcome_id: OutcomeEventId,
) -> RetractionResult:
    """Flip a confirmed outcome to retracted; report what happened (idempotent).

    Returns :attr:`RetractionResult.RETRACTED` on a successful flip,
    :attr:`~RetractionResult.ALREADY_RETRACTED` if it was already retracted,
    :attr:`~RetractionResult.NOT_CONFIRMED` if it is only an attempt (never retracted),
    or :attr:`~RetractionResult.NOT_FOUND` if no such outcome exists in the tenant scope.
    """
    existing = repository.get(tenant_id, outcome_id)
    if existing is None:
        return RetractionResult.NOT_FOUND
    if existing.signal_class is SignalClass.OUTCOME_RETRACTED:
        return RetractionResult.ALREADY_RETRACTED
    if existing.signal_class is not SignalClass.OUTCOME_CONFIRMED:
        return RetractionResult.NOT_CONFIRMED
    repository.retract(tenant_id, outcome_id)
    return RetractionResult.RETRACTED


__all__ = ["RetractionResult", "retract_outcome"]
