"""Digest model tests — aggregate-only, H7-required, raw/PII-forbidden.

The notify surface ships digests of *aggregates*: a number never appears without
its conservative confidence label (``minimum_tier`` + ``confidence_distribution``),
and no raw prompt/response/PII field is permitted to exist on a digest model
(``extra="forbid"`` + an explicit denylist validator).
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError
from valuemaxx.core import BindingTier, Provenance, TenantId
from valuemaxx.notify.models import Correction, Digest, DigestMetric


def _metric(**overrides: object) -> DigestMetric:
    base: dict[str, object] = {
        "name": "cost_per_outcome",
        "value": Decimal("1.50"),
        "unit": "usd",
        "minimum_tier": BindingTier.CANDIDATE,
        "confidence_distribution": {BindingTier.EXACT: 1, BindingTier.CANDIDATE: 50},
        "provenance_breakdown": {Provenance.MEASURED: Decimal("75.00")},
        "pct_unallocated": None,
    }
    base.update(overrides)
    return DigestMetric(**base)  # type: ignore[arg-type]


def test_digest_metric_requires_minimum_tier() -> None:
    """A DigestMetric cannot be constructed without minimum_tier (H7)."""
    with pytest.raises(ValidationError):
        DigestMetric(  # type: ignore[call-arg]
            name="x",
            value=Decimal("1"),
            unit="usd",
            confidence_distribution={BindingTier.EXACT: 1},
            provenance_breakdown={Provenance.MEASURED: Decimal("1")},
            pct_unallocated=None,
        )


def test_digest_metric_requires_confidence_distribution() -> None:
    """A DigestMetric cannot be constructed without confidence_distribution (H7)."""
    with pytest.raises(ValidationError):
        DigestMetric(  # type: ignore[call-arg]
            name="x",
            value=Decimal("1"),
            unit="usd",
            minimum_tier=BindingTier.EXACT,
            provenance_breakdown={Provenance.MEASURED: Decimal("1")},
            pct_unallocated=None,
        )


def test_digest_metric_minimum_tier_must_match_distribution() -> None:
    """minimum_tier must be the least-trusted present tier (H7 conservative)."""
    with pytest.raises(ValidationError):
        _metric(
            minimum_tier=BindingTier.EXACT,
            confidence_distribution={BindingTier.EXACT: 1, BindingTier.CANDIDATE: 3},
        )


def test_digest_metric_carries_both_h7_fields() -> None:
    """A valid metric round-trips both H7 fields, never collapsing them."""
    metric = _metric()
    assert metric.minimum_tier is BindingTier.CANDIDATE
    assert metric.confidence_distribution == {
        BindingTier.EXACT: 1,
        BindingTier.CANDIDATE: 50,
    }
    dumped = metric.model_dump_json()
    assert "minimum_tier" in dumped
    assert "confidence_distribution" in dumped


@pytest.mark.parametrize(
    "field_name",
    [
        "raw_prompt",
        "raw_response",
        "prompt",
        "response",
        "end_user_email",
        "customer_id",
        "user_id",
    ],
)
def test_digest_metric_forbids_raw_and_pii_fields(field_name: str) -> None:
    """No raw-content/PII field can be smuggled onto a digest (extra=forbid + denylist)."""
    with pytest.raises(ValidationError):
        _metric(**{field_name: "leaked"})


def test_digest_forbids_raw_and_pii_extra_fields() -> None:
    """The Digest envelope is extra-forbidding too — no raw content anywhere."""
    with pytest.raises(ValidationError):
        Digest(
            tenant_id=TenantId(uuid4()),
            period="2026-06",
            metrics=(),
            corrections=(),
            generated_at="2026-06-27T00:00:00Z",
            # extra=forbid rejects this raw field at runtime; suppress the static
            # "no such parameter" error so the test can assert the runtime guard.
            raw_prompt="leaked",  # type: ignore[call-arg]
        )


def test_digest_is_aggregate_only_and_carries_metrics() -> None:
    """A Digest carries its tenant, period, metrics, and corrections — no raw content."""
    digest = Digest(
        tenant_id=TenantId(uuid4()),
        period="2026-06",
        metrics=(_metric(),),
        corrections=(),
        generated_at="2026-06-27T00:00:00Z",
    )
    assert len(digest.metrics) == 1
    assert digest.metrics[0].minimum_tier is BindingTier.CANDIDATE


def test_correction_is_retraction_only() -> None:
    """A Correction is only ever emitted for an outcome_retracted event (H8)."""
    correction = Correction(
        metric_name="cost_per_outcome",
        previous_value=Decimal("1.50"),
        corrected_value=Decimal("2.00"),
        reason="outcome_retracted",
        affected_outcome_id="oe-123",
    )
    assert correction.reason == "outcome_retracted"
    with pytest.raises(ValidationError):
        Correction(
            metric_name="x",
            previous_value=Decimal("1"),
            corrected_value=Decimal("2"),
            # intentionally-invalid reason: the Literal rejects it at runtime, and
            # we suppress the static type error so the test can assert the runtime
            # guard fires (the whole point of the test).
            reason="some_other_reason",  # type: ignore[arg-type]
            affected_outcome_id="oe-1",
        )
