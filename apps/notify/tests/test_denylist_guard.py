"""The aggregate-only denylist guard rejects a model that DECLARES a raw/PII field.

``extra="forbid"`` stops a raw field passed at construction time, but the digest
models add a second, stronger guard: a model whose own schema *declares* a
denylisted field name is rejected when constructed. This is the structural backstop
for the ``notify_aggregate_only`` conformance rule — a future author cannot add a
``raw_prompt`` field and have it silently ship.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError
from valuemaxx.core import BindingTier, Provenance
from valuemaxx.notify.models import DigestMetric


def test_subclass_declaring_raw_field_is_rejected() -> None:
    """A DigestMetric subclass declaring a forbidden field raises on construction."""

    class LeakyMetric(DigestMetric):
        raw_prompt: str = "leaked"

    with pytest.raises(ValidationError):
        LeakyMetric(
            name="x",
            value=Decimal("1"),
            unit="usd",
            minimum_tier=BindingTier.EXACT,
            confidence_distribution={BindingTier.EXACT: 1},
            provenance_breakdown={Provenance.MEASURED: Decimal("1")},
            pct_unallocated=None,
        )
