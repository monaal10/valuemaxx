"""PG5 — gateway cost source: OpenRouter authoritative inline usage.cost (§5.5).

OpenRouter returns the actual billed ``usage.cost`` inline (no markup) — an
authoritative spend source, so the CostEvent is tagged ``provider_reconciled``
(per-attempt), with the gateway transaction id as the reconciliation record link.
The ``user`` field carries run attribution. We REFUSE any vendor *self-declared
estimate* — the design law is we never ship vendor-estimated cost as spend (§5.5).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from valuemaxx.capture.gateway import OpenRouterSource
from valuemaxx.core.enums import Provenance
from valuemaxx.core.errors import ProvenanceWarning
from valuemaxx.core.ids import TenantId

_TENANT = TenantId(uuid4())
_AT = datetime(2026, 6, 27, tzinfo=UTC)


class _FixedClock:
    def now(self) -> datetime:
        return _AT


def _openrouter_response(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "id": "gen-abc123",
        "model": "anthropic/claude-opus-4-8",
        "user": "run-42",  # the user field carries run attribution
        "usage": {
            "prompt_tokens": 1000,
            "completion_tokens": 500,
            "cost": "0.0123",  # authoritative inline billed cost
            "is_estimate": False,
        },
    }
    body.update(overrides)
    return body


def test_openrouter_authoritative_cost_is_provider_reconciled() -> None:
    """test_openrouter_authoritative_cost_is_provider_reconciled: inline cost -> reconciled."""
    source = OpenRouterSource(clock=_FixedClock())
    event = source.to_cost_event(_openrouter_response(), tenant_id=_TENANT)
    assert event.cost_usd == Decimal("0.0123")
    assert event.provenance.provenance is Provenance.PROVIDER_RECONCILED
    # reconciled provenance MUST carry a record id (the gateway transaction)
    assert event.provenance.reconciliation_record_id is not None
    assert "gen-abc123" in event.provenance.reconciliation_record_id


def test_openrouter_user_field_carries_run_attribution() -> None:
    """test_openrouter_user_field_carries_run_attribution: usage.user -> run_id."""
    source = OpenRouterSource(clock=_FixedClock())
    event = source.to_cost_event(_openrouter_response(), tenant_id=_TENANT)
    assert event.run_id == "run-42"


def test_openrouter_refuses_self_declared_estimate() -> None:
    """test_openrouter_refuses_self_declared_estimate: a vendor estimate is never spend (§5.5)."""
    source = OpenRouterSource(clock=_FixedClock())
    body = _openrouter_response()
    usage = body["usage"]
    assert isinstance(usage, dict)
    usage["is_estimate"] = True  # vendor self-declares the cost is an estimate
    with pytest.raises(ProvenanceWarning, match="estimate"):
        source.to_cost_event(body, tenant_id=_TENANT)


def test_openrouter_per_attempt_granularity() -> None:
    """test_openrouter_per_attempt_granularity: a gateway response is one attempt."""
    from valuemaxx.core.enums import CaptureGranularity

    source = OpenRouterSource(clock=_FixedClock())
    event = source.to_cost_event(_openrouter_response(), tenant_id=_TENANT)
    assert event.capture_granularity is CaptureGranularity.PER_ATTEMPT
