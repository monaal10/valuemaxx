"""ATTR-0 — the resolver framework + the resolver-emits-only-its-own-tier invariant.

A :class:`Resolver` is bound to exactly one :class:`~valuemaxx.core.BindingTier` it
may ever produce. Emitting a candidate carrying any other tier is an honesty-axis
violation — caught by the framework's validated ``resolve`` entrypoint, never
silently mis-labeled.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from _attribution_helpers import TENANT_A
from typing_extensions import override
from valuemaxx.attribution.resolver import (
    ResolveContext,
    ResolveOutcome,
    Resolver,
    no_match,
)
from valuemaxx.core import (
    AttributionCandidate,
    BindingTier,
    HonestyInvariantError,
    OutcomeEventId,
    RunId,
)


def _ctx() -> ResolveContext:
    return ResolveContext(
        tenant_id=TENANT_A,
        outcome_id=OutcomeEventId("oc-1"),
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        entity_keys=frozenset({("customer_id", "c-1")}),
        ambient_run_id=None,
        baggage={},
        echoed_run_id=None,
    )


class _ExactResolver(Resolver):
    tier = BindingTier.EXACT

    @override
    def _resolve(self, ctx: ResolveContext) -> ResolveOutcome:
        return self.matched_outcome(
            [self.candidate(run_id=RunId("run-1"), score=1.0, rationale="ambient")]
        )


class _ForeignTierResolver(Resolver):
    tier = BindingTier.LIKELY

    @override
    def _resolve(self, ctx: ResolveContext) -> ResolveOutcome:
        # Illegally emits a candidate carrying a tier other than the resolver's own.
        return ResolveOutcome(
            candidates=(
                AttributionCandidate(
                    run_id=RunId("run-1"),
                    tier=BindingTier.EXACT,  # foreign tier inside a LIKELY resolver
                    score=1.0,
                    rationale="bad",
                ),
            ),
            ambiguous=False,
        )


def test_resolver_declares_exactly_one_tier() -> None:
    """Each resolver exposes the single tier it is permitted to emit."""
    assert _ExactResolver().tier is BindingTier.EXACT


def test_candidate_helper_stamps_the_resolver_own_tier() -> None:
    """The ``candidate`` helper always stamps the resolver's own tier."""
    out = _ExactResolver().resolve(_ctx())
    assert out.matched is True
    assert len(out.candidates) == 1
    assert out.candidates[0].tier is BindingTier.EXACT


def test_no_match_yields_unmatched_outcome() -> None:
    """A no-match outcome carries zero candidates and is not matched."""
    out = no_match()
    assert out.matched is False
    assert out.candidates == ()
    assert out.ambiguous is False


def test_resolver_emitting_a_foreign_tier_is_rejected() -> None:
    """A resolver that emits a candidate with a foreign tier raises (honesty invariant)."""
    with pytest.raises(HonestyInvariantError):
        _ForeignTierResolver().resolve(_ctx())


def test_subclass_without_tier_is_rejected() -> None:
    """A Resolver subclass that forgets to declare ``tier`` is a hard error."""
    with pytest.raises(TypeError):

        class _NoTier(Resolver):  # pyright: ignore[reportUnusedClass]
            @override
            def _resolve(self, ctx: ResolveContext) -> ResolveOutcome:
                return no_match()


def test_matched_outcome_reports_matched_true() -> None:
    """An outcome with candidates is matched; without, it is not."""
    out = _ExactResolver().resolve(_ctx())
    assert out.matched is True
    assert no_match().matched is False
