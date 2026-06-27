"""Sink rendering tests — Slack/email digests render aggregates with H7 labels.

The sinks render a :class:`Digest` into a delivery payload. Two rules hold: every
metric line shows its ``minimum_tier`` (a number never renders bare), and the
rendered text carries no raw content (the model already forbids it structurally;
the renderer must not fabricate any).
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from valuemaxx.core import BindingTier, Provenance, TenantId
from valuemaxx.core.rollup import RollupConfidence
from valuemaxx.notify.builder import RollupView, build_digest
from valuemaxx.notify.sinks.email import render_email
from valuemaxx.notify.sinks.slack import render_slack


def _digest() -> object:
    view = RollupView(
        name="cost_per_outcome",
        value=Decimal("12.34"),
        unit="usd",
        confidence=RollupConfidence(
            minimum_tier=BindingTier.CANDIDATE,
            confidence_distribution={BindingTier.EXACT: 1, BindingTier.CANDIDATE: 50},
        ),
        provenance_breakdown={Provenance.MEASURED: Decimal("100")},
        pct_unallocated=None,
    )
    return build_digest(
        tenant_id=TenantId(uuid4()),
        period="2026-06",
        rollups=(view,),
        corrections=(),
        generated_at="2026-06-27T00:00:00Z",
    )


def test_slack_renders_minimum_tier() -> None:
    """The Slack payload shows each metric's minimum_tier (never a bare number)."""
    from valuemaxx.notify.models import Digest

    digest = _digest()
    assert isinstance(digest, Digest)
    payload = render_slack(digest)
    text = payload["text"]
    assert isinstance(text, str)
    assert "candidate" in text
    assert "cost_per_outcome" in text


def test_email_renders_minimum_tier() -> None:
    """The email body shows each metric's minimum_tier (never a bare number)."""
    from valuemaxx.notify.models import Digest

    digest = _digest()
    assert isinstance(digest, Digest)
    payload = render_email(digest)
    body = payload["body"]
    assert isinstance(body, str)
    assert "candidate" in body
    assert "cost_per_outcome" in body


def test_sink_renders_retraction_correction_line() -> None:
    """A digest carrying a retraction correction renders the correction in the payload."""
    from valuemaxx.notify.models import Correction, Digest

    view = RollupView(
        name="cost_per_outcome",
        value=Decimal("2.00"),
        unit="usd",
        confidence=RollupConfidence(
            minimum_tier=BindingTier.EXACT,
            confidence_distribution={BindingTier.EXACT: 3},
        ),
        provenance_breakdown={Provenance.MEASURED: Decimal("6")},
        pct_unallocated=None,
    )
    correction = Correction(
        metric_name="cost_per_outcome",
        previous_value=Decimal("1.50"),
        corrected_value=Decimal("2.00"),
        reason="outcome_retracted",
        affected_outcome_id="oe-99",
    )
    digest = build_digest(
        tenant_id=TenantId(uuid4()),
        period="2026-06",
        rollups=(view,),
        corrections=(correction,),
        generated_at="2026-06-27T00:00:00Z",
    )
    assert isinstance(digest, Digest)
    slack_text = render_slack(digest)["text"]
    email_body = render_email(digest)["body"]
    for rendered in (slack_text, email_body):
        assert "CORRECTION" in rendered
        assert "outcome_retracted" in rendered
        assert "oe-99" in rendered
