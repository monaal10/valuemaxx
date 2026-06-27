"""ATTR-1 — T2 baggage resolver (``exact``, run_id rides W3C baggage across hops).

T2 reads the ``run_id`` propagated on W3C baggage across live service hops (the
SDK injects the baggage map into the resolve context). When the baggage carries no
run id, T2 does not match — it never invents one.
"""

from __future__ import annotations

from datetime import UTC, datetime

from valuemaxx.attribution.binding.t2_baggage import BaggageResolver
from valuemaxx.attribution.resolver import ResolveContext
from valuemaxx.core import BindingTier, OutcomeEventId, RunId


def _ctx(*, baggage: dict[str, str]) -> ResolveContext:
    return ResolveContext(
        outcome_id=OutcomeEventId("oc-1"),
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        entity_keys=frozenset(),
        ambient_run_id=None,
        baggage=baggage,
        echoed_run_id=None,
    )


def test_tier_is_exact() -> None:
    """T2 may only ever emit the exact tier."""
    assert BaggageResolver().tier is BindingTier.EXACT


def test_binds_exact_from_baggage_run_id() -> None:
    """When baggage carries the run id key, T2 binds it as exact."""
    out = BaggageResolver().resolve(_ctx(baggage={"valuemaxx.run_id": "run-7"}))
    assert out.matched is True
    candidate = out.candidates[0]
    assert candidate.run_id == RunId("run-7")
    assert candidate.tier is BindingTier.EXACT


def test_no_match_when_baggage_has_no_run_id() -> None:
    """Baggage without the run id key does not match."""
    out = BaggageResolver().resolve(_ctx(baggage={"other": "value"}))
    assert out.matched is False
    assert out.candidates == ()


def test_no_match_on_empty_baggage() -> None:
    """Empty baggage does not match."""
    assert BaggageResolver().resolve(_ctx(baggage={})).matched is False


def test_blank_baggage_value_does_not_match() -> None:
    """A present-but-blank baggage run id is treated as absent (never binds empty)."""
    out = BaggageResolver().resolve(_ctx(baggage={"valuemaxx.run_id": "  "}))
    assert out.matched is False
