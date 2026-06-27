"""F0-CORE-1b: CostEvent — one HTTP attempt, idempotency key, PTU None cost."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from atm_core.cost import CostEvent
from atm_core.enums import CaptureGranularity, Provenance
from atm_core.ids import AttemptId, CostEventId, RunId, TenantId
from atm_core.provenance import ProvenanceLabel
from atm_core.tokens import TokenVector
from pydantic import ValidationError


def _tokens() -> TokenVector:
    return TokenVector(
        input_uncached=10,
        cache_read=0,
        cache_write_5m=0,
        cache_write_1h=0,
        output=5,
        reasoning=0,
    )


def _event(**overrides: object) -> CostEvent:
    base: dict[str, object] = {
        "tenant_id": TenantId(uuid4()),
        "id": CostEventId("ce-1"),
        "run_id": RunId("run-1"),
        "attempt_id": AttemptId("att-1"),
        "provider": "anthropic",
        "model": "claude-opus-4-8",
        "tokens": _tokens(),
        "capture_granularity": CaptureGranularity.PER_ATTEMPT,
        "provenance": ProvenanceLabel(provenance=Provenance.MEASURED),
        "cost_usd": Decimal("0.12"),
        "is_streaming": False,
        "partial_recovered": False,
        "billing_uncertain_abort": False,
        "provenance_warnings": (),
        "occurred_at": datetime.now(tz=UTC),
    }
    base.update(overrides)
    return CostEvent(**base)  # type: ignore[arg-type]


def test_idempotency_key_is_run_and_attempt() -> None:
    """T-CE-1: dedup key = (run_id, attempt_id) (§5.2 M7)."""
    ev = _event()
    assert ev.idempotency_key == (RunId("run-1"), AttemptId("att-1"))


def test_cost_usd_may_be_none_for_ptu() -> None:
    """T-CE-2: cost_usd is None for PTU/billing-uncertain — never fabricated (H10)."""
    ev = _event(cost_usd=None, billing_uncertain_abort=True)
    assert ev.cost_usd is None


def test_cost_event_requires_tenant() -> None:
    with pytest.raises(ValidationError):
        CostEvent(  # type: ignore[call-arg]
            id=CostEventId("ce-1"),
            run_id=RunId("run-1"),
            attempt_id=AttemptId("att-1"),
            provider="anthropic",
            model="claude-opus-4-8",
            tokens=_tokens(),
            capture_granularity=CaptureGranularity.PER_ATTEMPT,
            provenance=ProvenanceLabel(provenance=Provenance.MEASURED),
            cost_usd=None,
            is_streaming=False,
            partial_recovered=False,
            billing_uncertain_abort=False,
            provenance_warnings=(),
            occurred_at=datetime.now(tz=UTC),
        )


def test_cost_event_is_frozen() -> None:
    ev = _event()
    with pytest.raises(ValidationError):
        ev.provider = "openai"  # frozen
