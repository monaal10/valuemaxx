"""ATTR-2 — T4 entity-match resolver (``candidate``; the T3-echo Phase-1 fallback).

T4 binds via a shared durable entity id (``customer_id``/``order_id``), querying
``RunRepository.list_by_entity`` within a ±window of the outcome time and
tie-breaking by time proximity. It is the labeled fallback when T3's round-trip
echo is absent (§6.3). It produces only the ``candidate`` tier; an ε-tie (two runs
indistinguishably close) sets ``ambiguous=True`` so the cascade halts the outcome
to human review rather than guessing. It never promotes to deterministic.
"""

from __future__ import annotations

from datetime import timedelta

from _attribution_helpers import (
    TENANT_A,
    TENANT_B,
    InMemoryRunRepository,
    make_run,
    utc,
)
from valuemaxx.attribution.binding.t4_entity import EntityMatchResolver
from valuemaxx.attribution.resolver import ResolveContext
from valuemaxx.core import BindingTier, OutcomeEventId, RunId

_WINDOW = timedelta(hours=6)
_OCCURRED = utc(2026, 1, 1, 12, 0)


def _resolver(repo: InMemoryRunRepository) -> EntityMatchResolver:
    return EntityMatchResolver(run_repo=repo, window=_WINDOW, epsilon=timedelta(seconds=1))


def _ctx(
    *,
    tenant_id: object = TENANT_A,
    entity_keys: frozenset[tuple[str, str]] = frozenset({("customer_id", "c-1")}),
) -> ResolveContext:
    return ResolveContext(
        tenant_id=tenant_id,  # type: ignore[arg-type]  # TenantId is a UUID NewType
        outcome_id=OutcomeEventId("oc-1"),
        occurred_at=_OCCURRED,
        entity_keys=entity_keys,
        ambient_run_id=None,
        baggage={},
        echoed_run_id=None,
    )


def test_tier_is_candidate() -> None:
    """T4 may only ever emit the candidate tier."""
    assert EntityMatchResolver(run_repo=InMemoryRunRepository(), window=_WINDOW).tier is (
        BindingTier.CANDIDATE
    )


def test_single_match_yields_one_candidate() -> None:
    """A single run sharing the entity key inside the window binds as a candidate."""
    repo = InMemoryRunRepository()
    repo.upsert(
        TENANT_A,
        make_run(
            run_id="run-1",
            started_at=utc(2026, 1, 1, 11, 0),
            entity_keys=frozenset({("customer_id", "c-1")}),
        ),
    )
    out = _resolver(repo).resolve(_ctx())
    assert out.matched is True
    assert out.ambiguous is False
    assert len(out.candidates) == 1
    assert out.candidates[0].run_id == RunId("run-1")
    assert out.candidates[0].tier is BindingTier.CANDIDATE


def test_no_match_when_no_run_shares_entity() -> None:
    """No run with the entity key => no match."""
    out = _resolver(InMemoryRunRepository()).resolve(_ctx())
    assert out.matched is False
    assert out.candidates == ()


def test_runs_outside_window_are_excluded() -> None:
    """A run sharing the entity but outside the ±window is not a candidate."""
    repo = InMemoryRunRepository()
    repo.upsert(
        TENANT_A,
        make_run(
            run_id="far",
            started_at=utc(2026, 1, 1, 1, 0),  # 11h before, > 6h window
            entity_keys=frozenset({("customer_id", "c-1")}),
        ),
    )
    assert _resolver(repo).resolve(_ctx()).matched is False


def test_time_window_tie_break_closer_scores_higher() -> None:
    """Two in-window runs both return; the time-closer run scores higher."""
    repo = InMemoryRunRepository()
    repo.upsert(
        TENANT_A,
        make_run(
            run_id="closer",
            started_at=utc(2026, 1, 1, 11, 30),  # 30m before
            entity_keys=frozenset({("customer_id", "c-1")}),
        ),
    )
    repo.upsert(
        TENANT_A,
        make_run(
            run_id="farther",
            started_at=utc(2026, 1, 1, 9, 0),  # 3h before
            entity_keys=frozenset({("customer_id", "c-1")}),
        ),
    )
    out = _resolver(repo).resolve(_ctx())
    assert out.ambiguous is False
    assert len(out.candidates) == 2
    by_run = {c.run_id: c for c in out.candidates}
    assert by_run[RunId("closer")].score > by_run[RunId("farther")].score
    assert all(c.tier is BindingTier.CANDIDATE for c in out.candidates)


def test_epsilon_tie_sets_ambiguous() -> None:
    """Two runs indistinguishably close (within epsilon) flag ambiguity (halt to review)."""
    repo = InMemoryRunRepository()
    # Both exactly equidistant from the outcome time => an epsilon tie.
    repo.upsert(
        TENANT_A,
        make_run(
            run_id="a",
            started_at=utc(2026, 1, 1, 11, 0),  # 1h before
            entity_keys=frozenset({("customer_id", "c-1")}),
        ),
    )
    repo.upsert(
        TENANT_A,
        make_run(
            run_id="b",
            started_at=utc(2026, 1, 1, 13, 0),  # 1h after
            entity_keys=frozenset({("customer_id", "c-1")}),
        ),
    )
    out = _resolver(repo).resolve(_ctx())
    assert out.ambiguous is True
    assert {c.run_id for c in out.candidates} == {RunId("a"), RunId("b")}
    assert all(c.tier is BindingTier.CANDIDATE for c in out.candidates)


def test_tenant_scoped_other_tenant_never_returned() -> None:
    """A run under a different tenant is never a candidate (structural isolation)."""
    repo = InMemoryRunRepository()
    repo.upsert(
        TENANT_B,
        make_run(
            run_id="other-tenant",
            tenant_id=TENANT_B,
            started_at=utc(2026, 1, 1, 11, 30),
            entity_keys=frozenset({("customer_id", "c-1")}),
        ),
    )
    out = _resolver(repo).resolve(_ctx(tenant_id=TENANT_A))
    assert out.matched is False


def test_only_candidate_tier_across_multiple_entity_keys() -> None:
    """Runs found via different entity keys still only ever carry candidate tier."""
    repo = InMemoryRunRepository()
    repo.upsert(
        TENANT_A,
        make_run(
            run_id="via-order",
            started_at=utc(2026, 1, 1, 11, 45),
            entity_keys=frozenset({("order_id", "o-9")}),
        ),
    )
    out = _resolver(repo).resolve(
        _ctx(entity_keys=frozenset({("customer_id", "c-1"), ("order_id", "o-9")}))
    )
    assert out.matched is True
    assert all(c.tier is BindingTier.CANDIDATE for c in out.candidates)


def test_same_run_via_two_keys_is_deduplicated() -> None:
    """A run matched via two of the outcome's entity keys appears once, not twice."""
    repo = InMemoryRunRepository()
    repo.upsert(
        TENANT_A,
        make_run(
            run_id="dup",
            started_at=utc(2026, 1, 1, 11, 45),
            entity_keys=frozenset({("customer_id", "c-1"), ("order_id", "o-9")}),
        ),
    )
    out = _resolver(repo).resolve(
        _ctx(entity_keys=frozenset({("customer_id", "c-1"), ("order_id", "o-9")}))
    )
    assert len(out.candidates) == 1
    assert out.candidates[0].run_id == RunId("dup")
