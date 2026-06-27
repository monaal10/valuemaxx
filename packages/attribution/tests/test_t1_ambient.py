"""ATTR-1 — T1 ambient-context resolver (``exact``, only when context propagated).

T1 reads the active ``run_id`` off the ``valuemaxx.core`` ambient contextvar when
the outcome fires in-process. When the contextvar is unset (e.g. a thread-pool or
fork hop dropped it, H10), T1 returns ``matched=False`` rather than guessing — an
absent context is never silently mis-bound.
"""

from __future__ import annotations

from datetime import UTC, datetime

from _attribution_helpers import TENANT_A
from valuemaxx.attribution.binding.t1_ambient import AmbientContextResolver
from valuemaxx.attribution.resolver import ResolveContext
from valuemaxx.core import BindingTier, OutcomeEventId, RunId, active_run_id


def _ctx(*, ambient_run_id: RunId | None) -> ResolveContext:
    return ResolveContext(
        tenant_id=TENANT_A,
        outcome_id=OutcomeEventId("oc-1"),
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        entity_keys=frozenset(),
        ambient_run_id=ambient_run_id,
        baggage={},
        echoed_run_id=None,
    )


def test_tier_is_exact() -> None:
    """T1 may only ever emit the exact tier."""
    assert AmbientContextResolver().tier is BindingTier.EXACT


def test_binds_exact_when_ambient_present() -> None:
    """When the ambient run id is present, T1 binds it as exact."""
    out = AmbientContextResolver().resolve(_ctx(ambient_run_id=RunId("run-42")))
    assert out.matched is True
    assert len(out.candidates) == 1
    candidate = out.candidates[0]
    assert candidate.run_id == RunId("run-42")
    assert candidate.tier is BindingTier.EXACT
    assert candidate.score == 1.0


def test_no_match_when_ambient_absent() -> None:
    """When no ambient run id is set, T1 does not match (never mis-binds)."""
    out = AmbientContextResolver().resolve(_ctx(ambient_run_id=None))
    assert out.matched is False
    assert out.candidates == ()


def test_reads_from_core_contextvar_when_context_unset_on_ctx() -> None:
    """T1 falls back to the live core contextvar if the context carries no ambient id.

    The cascade snapshots the ambient id into ``ResolveContext.ambient_run_id`` at
    capture time; this guards the in-process direct-call path where the resolver is
    invoked while the contextvar is still live.
    """
    token = active_run_id.set(RunId("live-run"))
    try:
        out = AmbientContextResolver().resolve(_ctx(ambient_run_id=None))
    finally:
        active_run_id.reset(token)
    assert out.matched is True
    assert out.candidates[0].run_id == RunId("live-run")
    assert out.candidates[0].tier is BindingTier.EXACT


def test_context_snapshot_takes_precedence_over_live_var() -> None:
    """An explicit snapshot on the context wins over the live contextvar."""
    token = active_run_id.set(RunId("live-run"))
    try:
        out = AmbientContextResolver().resolve(_ctx(ambient_run_id=RunId("snapshot-run")))
    finally:
        active_run_id.reset(token)
    assert out.candidates[0].run_id == RunId("snapshot-run")
