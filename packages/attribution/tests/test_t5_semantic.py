"""ATTR-3 — T5 semantic-inference resolver (``likely``; off without a judge).

The labeled last resort (§6.3): an LLM-judge reasons over entity + time + content
to bind outcomes that happen entirely in an external UI with no shared id. It is
the lowest-trust tier — it produces only the ``likely`` tier, is ALWAYS review-
queued by the cascade, and is NEVER fed to billing-grade metrics.

Without an injected judge the resolver is DISABLED (``matched=False``); it never
falls back to a real model — tests inject a deterministic fake.
"""

from __future__ import annotations

from datetime import timedelta

from valuemaxx.attribution.inference.t5_semantic import SemanticInferenceResolver
from valuemaxx.attribution.resolver import ResolveContext
from valuemaxx.core import BindingTier, OutcomeEventId, RunId

from tests.conftest import (
    TENANT_A,
    InMemoryRunRepository,
    StubLlmJudge,
    make_run,
    utc,
)

_WINDOW = timedelta(hours=24)
_OCCURRED = utc(2026, 1, 1, 12, 0)


def _ctx(
    *,
    entity_keys: frozenset[tuple[str, str]] = frozenset({("customer_id", "c-1")}),
    content: str = "customer reported the bug is fixed",
) -> ResolveContext:
    return ResolveContext(
        tenant_id=TENANT_A,
        outcome_id=OutcomeEventId("oc-1"),
        occurred_at=_OCCURRED,
        entity_keys=entity_keys,
        ambient_run_id=None,
        baggage={},
        echoed_run_id=None,
        content=content,
    )


def _repo_with_one_run() -> InMemoryRunRepository:
    repo = InMemoryRunRepository()
    repo.upsert(
        TENANT_A,
        make_run(run_id="run-1", started_at=utc(2026, 1, 1, 11, 0),
                 entity_keys=frozenset({("customer_id", "c-1")})),
    )
    return repo


def test_tier_is_likely() -> None:
    """T5 may only ever emit the likely tier."""
    resolver = SemanticInferenceResolver(
        run_repo=InMemoryRunRepository(), judge=StubLlmJudge(0.9), window=_WINDOW
    )
    assert resolver.tier is BindingTier.LIKELY


def test_disabled_without_judge() -> None:
    """With no injected judge, T5 is disabled and never matches."""
    resolver = SemanticInferenceResolver(
        run_repo=_repo_with_one_run(), judge=None, window=_WINDOW
    )
    out = resolver.resolve(_ctx())
    assert out.matched is False
    assert out.candidates == ()


def test_binds_likely_when_judge_scores_above_threshold() -> None:
    """A judge score above threshold yields a likely candidate."""
    judge = StubLlmJudge(0.95)
    resolver = SemanticInferenceResolver(
        run_repo=_repo_with_one_run(), judge=judge, window=_WINDOW, threshold=0.5
    )
    out = resolver.resolve(_ctx())
    assert out.matched is True
    assert len(out.candidates) == 1
    assert out.candidates[0].run_id == RunId("run-1")
    assert out.candidates[0].tier is BindingTier.LIKELY
    assert out.candidates[0].score == 0.95
    assert judge.calls, "the injected judge must have been consulted"


def test_no_match_when_judge_scores_below_threshold() -> None:
    """A judge score below threshold is not a likely candidate."""
    resolver = SemanticInferenceResolver(
        run_repo=_repo_with_one_run(), judge=StubLlmJudge(0.1), window=_WINDOW, threshold=0.5
    )
    out = resolver.resolve(_ctx())
    assert out.matched is False


def test_no_candidate_runs_yields_no_match() -> None:
    """No candidate runs in scope => no match even with a permissive judge."""
    resolver = SemanticInferenceResolver(
        run_repo=InMemoryRunRepository(), judge=StubLlmJudge(0.99), window=_WINDOW
    )
    assert resolver.resolve(_ctx()).matched is False


def test_emits_only_likely_tier_for_all_candidates() -> None:
    """Every candidate T5 emits carries the likely tier."""
    repo = InMemoryRunRepository()
    for i in range(3):
        repo.upsert(
            TENANT_A,
            make_run(run_id=f"run-{i}", started_at=utc(2026, 1, 1, 11, i),
                     entity_keys=frozenset({("customer_id", "c-1")})),
        )
    resolver = SemanticInferenceResolver(
        run_repo=repo, judge=StubLlmJudge(0.8), window=_WINDOW, threshold=0.5
    )
    out = resolver.resolve(_ctx())
    assert len(out.candidates) == 3
    assert all(c.tier is BindingTier.LIKELY for c in out.candidates)
