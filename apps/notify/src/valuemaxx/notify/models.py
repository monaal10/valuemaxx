"""Digest models — aggregate-only sinks that never carry raw content or PII.

The notify surface emits *digests*: rollups of aggregate metrics for Slack/email.
Two honesty rules are structural here, not disciplinary:

* **H7 — a number never appears without its confidence.** ``DigestMetric`` requires
  both ``minimum_tier`` (the least-trusted present tier, the headline label) and
  ``confidence_distribution`` (the per-tier counts), and a validator asserts the
  minimum is consistent with the distribution — a surface can never silently
  collapse a mixed-confidence aggregate into a clean-looking single number.
* **No raw content / PII.** Every model is ``extra="forbid"`` AND a validator
  rejects any field whose name matches a raw-content/PII denylist, so a digest can
  never carry a prompt, response, email, or customer/user id (conformance:
  ``notify_aggregate_only``).

Corrections (H8) are emitted only for a retracted outcome: when a confirmed outcome
flips to ``outcome_retracted`` it is removed from the cost-per-outcome denominator
and the next cycle emits a :class:`Correction` rather than silently restating.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Literal

from pydantic import model_validator
from valuemaxx.core import BindingTier, Provenance
from valuemaxx.core.base import StrictModel, TenantScopedModel
from valuemaxx.core.rollup import RollupConfidence

if TYPE_CHECKING:
    from typing import Self

# Field-name fragments that may never appear on a digest model: raw model content
# and personally-identifying data. Matched as substrings so e.g. ``raw_prompt``,
# ``end_user_email``, and ``customer_id`` are all caught.
_FORBIDDEN_FIELD_MARKERS: tuple[str, ...] = (
    "raw",
    "prompt",
    "response",
    "email",
    "customer_id",
    "user_id",
    "pii",
    "content",
)


def _assert_no_raw_or_pii_fields(model: StrictModel) -> None:
    """Raise if any set field name matches the raw-content/PII denylist."""
    for field_name in type(model).model_fields:
        lowered = field_name.lower()
        if any(marker in lowered for marker in _FORBIDDEN_FIELD_MARKERS):
            raise ValueError(
                f"digest model {type(model).__name__!r} declares a forbidden "
                f"raw-content/PII field {field_name!r} (notify is aggregate-only)"
            )


class DigestMetric(StrictModel):
    """One aggregate metric in a digest — value plus its conservative confidence.

    Both H7 fields are required (no default): a metric cannot be built without its
    ``minimum_tier`` and ``confidence_distribution``. The validator asserts the
    minimum equals the least-trusted present tier, so the headline label can never
    understate the mixed confidence behind the number.
    """

    name: str
    value: Decimal
    unit: str
    minimum_tier: BindingTier
    confidence_distribution: dict[BindingTier, int]
    provenance_breakdown: dict[Provenance, Decimal]
    pct_unallocated: Decimal | None

    @model_validator(mode="after")
    def _validate_aggregate_only_and_confidence(self) -> Self:
        _assert_no_raw_or_pii_fields(self)
        # Reuse the core H7 invariant: minimum_tier must be the least-trusted
        # present tier. Constructing RollupConfidence raises on inconsistency.
        RollupConfidence(
            minimum_tier=self.minimum_tier,
            confidence_distribution=self.confidence_distribution,
        )
        return self


class Correction(StrictModel):
    """A correction emitted when an outcome is retracted (H8) — never silent.

    A retracted outcome is removed from the cost-per-outcome denominator and the
    next digest cycle restates the affected metric with an explicit correction. The
    only legal reason is ``outcome_retracted`` (a ``Literal``), so a correction can
    never be repurposed to quietly revise a number for any other cause.
    """

    metric_name: str
    previous_value: Decimal
    corrected_value: Decimal
    reason: Literal["outcome_retracted"]
    affected_outcome_id: str


class Digest(TenantScopedModel):
    """A tenant-scoped digest of aggregate metrics plus any retraction corrections.

    Aggregate-only and ``extra="forbid"``: there is no field through which a raw
    prompt/response or PII could be attached. Each carried :class:`DigestMetric`
    keeps its own H7 label, so the envelope never collapses per-metric confidence.
    """

    period: str
    metrics: tuple[DigestMetric, ...]
    corrections: tuple[Correction, ...]
    generated_at: str

    @model_validator(mode="after")
    def _validate_aggregate_only(self) -> Self:
        _assert_no_raw_or_pii_fields(self)
        return self


__all__ = ["Correction", "Digest", "DigestMetric"]
