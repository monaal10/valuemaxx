"""PG5 — provider Cost API marker source + the PTU billing-uncertain refusal (§5.3, H10).

The provider Cost API (OpenAI Costs, Anthropic cost_report) is a *marker* source:
it signals that a (provider, project, model, day) bucket exists to reconcile, but
the actual estimate->invoice true-up lives in the reconciliation package, not
here. ``is_marker_source`` makes that contract explicit.

This module owns the H10 refusal: a provisioned-throughput (PTU) attempt is billed
by reserved capacity, not per token, so the per-token rate does NOT reflect actual
spend. We therefore emit a CostEvent with ``cost_usd=None`` and the
``billing_uncertain_abort: provisioned_throughput`` warning — capturing the real
token vector while refusing to fabricate a token x price (never a silent zero).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from valuemaxx.capture.invariants import price_or_abort
from valuemaxx.core.cost import CostEvent
from valuemaxx.core.enums import CaptureGranularity, Provenance
from valuemaxx.core.ids import AttemptId, CostEventId, RunId
from valuemaxx.core.provenance import ProvenanceLabel

if TYPE_CHECKING:
    from valuemaxx.core.context import Clock
    from valuemaxx.core.ids import TenantId
    from valuemaxx.core.tokens import TokenVector


def is_marker_source() -> bool:
    """True — the provider Cost API marks buckets for recon; it is not a spend source.

    The authoritative daily true-up is performed by the reconciliation package
    against this marker; capture never treats the provider Cost API as the cost of
    a single attempt.
    """
    return True


def ptu_cost_event(
    tokens: TokenVector,
    *,
    tenant_id: TenantId,
    provider: str,
    model: str,
    run_id: str,
    attempt_id: str,
    clock: Clock,
) -> CostEvent:
    """Build a CostEvent for a provisioned-throughput attempt: cost_usd=None + warning (H10).

    The token vector is captured faithfully; ``cost_usd`` is ``None`` because a PTU
    attempt has no metered per-token price, and the warnings carry
    ``billing_uncertain_abort: provisioned_throughput`` so the refusal is explicit.
    """
    cost_usd, warnings = price_or_abort(
        tokens, None, billing_uncertain=False, provisioned_throughput=True
    )
    return CostEvent(
        tenant_id=tenant_id,
        id=CostEventId(f"{run_id}:{attempt_id}"),
        run_id=RunId(run_id),
        attempt_id=AttemptId(attempt_id),
        provider=provider,
        model=model,
        tokens=tokens,
        capture_granularity=CaptureGranularity.PER_ATTEMPT,
        provenance=ProvenanceLabel(provenance=Provenance.MEASURED),
        cost_usd=cost_usd,
        is_streaming=False,
        partial_recovered=False,
        billing_uncertain_abort=True,
        provenance_warnings=warnings,
        occurred_at=clock.now(),
    )


__all__ = ["is_marker_source", "ptu_cost_event"]
