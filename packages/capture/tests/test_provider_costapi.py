"""PG5 — provider_costapi: a marker source + the PTU billing-uncertain refusal (§5.3, H10).

The provider Cost API is a marker/reconciliation source — the actual daily true-up
lives in the reconciliation package. Here we own the H10 refusal: a
provisioned-throughput (PTU) attempt has no metered per-token cost, so its
CostEvent carries ``cost_usd=None`` and the ``billing_uncertain_abort:
provisioned_throughput`` warning — never a fabricated token x price.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from valuemaxx.capture.invariants import PROVISIONED_THROUGHPUT_REASON
from valuemaxx.capture.provider_costapi import is_marker_source, ptu_cost_event
from valuemaxx.core.ids import TenantId
from valuemaxx.core.tokens import TokenVector

_TENANT = TenantId(uuid4())
_AT = datetime(2026, 6, 27, tzinfo=UTC)


class _FixedClock:
    def now(self) -> datetime:
        return _AT


def _tokens() -> TokenVector:
    return TokenVector(
        input_uncached=1_000_000,
        cache_read=0,
        cache_write_5m=0,
        cache_write_1h=0,
        output=1_000_000,
        reasoning=0,
    )


def test_provider_costapi_is_a_marker_source() -> None:
    """test_provider_costapi_is_a_marker_source: it marks for recon, not a spend source."""
    assert is_marker_source() is True


def test_ptu_attempt_refuses_token_derived_cost() -> None:
    """test_ptu_attempt_refuses_token_derived_cost: PTU -> cost_usd=None + warning (H10)."""
    event = ptu_cost_event(
        _tokens(),
        tenant_id=_TENANT,
        provider="bedrock",
        model="anthropic.claude-opus-4-8",
        run_id="run-ptu",
        attempt_id="att-ptu",
        clock=_FixedClock(),
    )
    assert event.cost_usd is None  # NEVER token x price under provisioned throughput
    assert event.billing_uncertain_abort is True
    assert any(PROVISIONED_THROUGHPUT_REASON in w for w in event.provenance_warnings)
    assert any("billing_uncertain_abort" in w for w in event.provenance_warnings)


def test_ptu_event_still_carries_token_vector() -> None:
    """test_ptu_event_still_carries_token_vector: tokens are captured even with no cost."""
    event = ptu_cost_event(
        _tokens(),
        tenant_id=_TENANT,
        provider="bedrock",
        model="anthropic.claude-opus-4-8",
        run_id="run-ptu",
        attempt_id="att-ptu",
        clock=_FixedClock(),
    )
    assert event.tokens.input_uncached == 1_000_000
    assert event.cost_usd is None
    # the token vector is real even though cost is honestly unknown
    assert event.tokens.output == 1_000_000
    assert isinstance(event.tokens.total_input, int)
    assert event.cost_usd != Decimal("0")  # not a silent zero either
