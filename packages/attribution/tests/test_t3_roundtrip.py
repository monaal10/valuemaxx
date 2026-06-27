"""ATTR-1 — T3 round-trip-id resolver (``deterministic``, echoed run_id).

T3 reads the ``run_id`` the agent stamped into an outbound external object
(Stripe metadata, ticket custom field) that the later webhook **echoes back** in
the outcome's metadata (§6.3, H4). When the echo is absent (the external system
does not echo metadata, e.g. Salesforce), T3 does not match — the outcome falls
through to T4 entity-match, never silently mis-bound.
"""

from __future__ import annotations

from datetime import UTC, datetime

from valuemaxx.attribution.binding.t3_roundtrip import RoundTripResolver
from valuemaxx.attribution.resolver import ResolveContext
from valuemaxx.core import BindingTier, OutcomeEventId, RunId

from tests.conftest import TENANT_A


def _ctx(*, echoed_run_id: RunId | None) -> ResolveContext:
    return ResolveContext(
        tenant_id=TENANT_A,
        outcome_id=OutcomeEventId("oc-1"),
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        entity_keys=frozenset(),
        ambient_run_id=None,
        baggage={},
        echoed_run_id=echoed_run_id,
    )


def test_tier_is_deterministic() -> None:
    """T3 may only ever emit the deterministic tier."""
    assert RoundTripResolver().tier is BindingTier.DETERMINISTIC


def test_binds_deterministic_when_echo_present() -> None:
    """An echoed run id binds deterministically."""
    out = RoundTripResolver().resolve(_ctx(echoed_run_id=RunId("run-99")))
    assert out.matched is True
    candidate = out.candidates[0]
    assert candidate.run_id == RunId("run-99")
    assert candidate.tier is BindingTier.DETERMINISTIC
    assert candidate.score == 1.0


def test_no_match_without_echo() -> None:
    """No echoed run id => no match (falls through to T4 entity-match)."""
    out = RoundTripResolver().resolve(_ctx(echoed_run_id=None))
    assert out.matched is False
    assert out.candidates == ()
