"""ATTR-4 — the cascade orchestrator (exact -> deterministic -> candidate -> likely).

``Cascade.bind`` walks the resolvers in tier order, first match wins, every result
labeled (§6.3):

- A deterministic match (T1/T2/T3) short-circuits to a billing-grade result with
  ``review_required=False`` — but only after **fast-path revalidation** confirms
  the run still exists; a dangling run id is downgraded (never bind a ghost).
- T4 candidate / T5 likely are advisory: ``review_required=True`` and enqueued;
  they are NEVER billing-grade.
- T4 ambiguity HALTS and enqueues all tied candidates.
- No match => unbound, review-required.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from valuemaxx.attribution.cascade import Cascade
from valuemaxx.core import (
    BindingTier,
    OutcomeBinding,
    OutcomeEvent,
    OutcomeEventId,
    RunId,
    SignalClass,
)

from tests.conftest import (
    TENANT_A,
    InMemoryReviewQueue,
    InMemoryRunRepository,
    StubLlmJudge,
    make_run,
    utc,
)

_OCCURRED = utc(2026, 1, 1, 12, 0)


def _outcome(
    *,
    entity_keys: frozenset[tuple[str, str]] = frozenset({("customer_id", "c-1")}),
    content: str = "the deal closed",
) -> OutcomeEvent:
    return OutcomeEvent(
        tenant_id=TENANT_A,
        id=OutcomeEventId("oc-1"),
        name="deal_closed",
        signal_class=SignalClass.OUTCOME_CONFIRMED,
        value=Decimal("100.00"),
        occurred_at=_OCCURRED,
        binding=OutcomeBinding(run_id=None, tier=None, bound_by=None),
        entity_keys=entity_keys,
        correlation_id=None,
        source="crm",
        raw={"content": content},
    )


def _cascade(
    repo: InMemoryRunRepository,
    queue: InMemoryReviewQueue,
    *,
    judge: StubLlmJudge | None = None,
    window: timedelta = timedelta(hours=6),
) -> Cascade:
    return Cascade(
        run_repo=repo,
        review_queue=queue,
        judge=judge,
        entity_window=window,
    )


def _seed_run(repo: InMemoryRunRepository, run_id: str, *, minute_offset: int = 0) -> None:
    repo.upsert(
        TENANT_A,
        make_run(
            run_id=run_id,
            started_at=_OCCURRED + timedelta(minutes=minute_offset),
            entity_keys=frozenset({("customer_id", "c-1")}),
        ),
    )


# --- deterministic short-circuit -------------------------------------------------


def test_ambient_exact_short_circuits_billing_grade() -> None:
    """A live ambient run id binds exact, billing-grade, no review."""
    repo = InMemoryRunRepository()
    _seed_run(repo, "run-1")
    queue = InMemoryReviewQueue()
    result = _cascade(repo, queue).bind(_outcome(), ambient_run_id=RunId("run-1"))
    assert result.tier is BindingTier.EXACT
    assert result.run_id == RunId("run-1")
    assert result.review_required is False
    assert result.is_billing_grade is True
    assert queue.list_pending(TENANT_A) == []


def test_deterministic_short_circuits_before_entity() -> None:
    """T1 (exact) wins over T4 (candidate): order is honored, first match short-circuits."""
    repo = InMemoryRunRepository()
    _seed_run(repo, "ambient-run")
    _seed_run(repo, "entity-run", minute_offset=1)
    queue = InMemoryReviewQueue()
    result = _cascade(repo, queue).bind(_outcome(), ambient_run_id=RunId("ambient-run"))
    assert result.tier is BindingTier.EXACT
    assert result.run_id == RunId("ambient-run")
    assert result.bound_by == "AmbientContextResolver"


def test_roundtrip_deterministic_binds_billing_grade() -> None:
    """A T3 echo binds deterministic + billing-grade with no review."""
    repo = InMemoryRunRepository()
    _seed_run(repo, "echo-run")
    queue = InMemoryReviewQueue()
    result = _cascade(repo, queue).bind(_outcome(), echoed_run_id=RunId("echo-run"))
    assert result.tier is BindingTier.DETERMINISTIC
    assert result.is_billing_grade is True
    assert result.review_required is False


# --- fast-path revalidation (never bind a ghost) --------------------------------


def test_dangling_deterministic_run_is_downgraded_not_bound() -> None:
    """A deterministic run id that no longer exists is NOT bound — it downgrades."""
    repo = InMemoryRunRepository()  # ambient run id is NOT seeded => dangling
    _seed_run(repo, "entity-run")  # but an entity-match run exists
    queue = InMemoryReviewQueue()
    result = _cascade(repo, queue).bind(_outcome(), ambient_run_id=RunId("ghost-run"))
    # The ghost is refused; the cascade falls through to T4 entity-match (candidate).
    assert result.run_id != RunId("ghost-run")
    assert result.tier is BindingTier.CANDIDATE
    assert result.is_billing_grade is False
    assert result.review_required is True


def test_dangling_deterministic_with_no_fallback_is_unbound() -> None:
    """A dangling deterministic id with no lower-tier match yields an unbound result."""
    repo = InMemoryRunRepository()  # nothing seeded
    queue = InMemoryReviewQueue()
    result = _cascade(repo, queue).bind(
        _outcome(entity_keys=frozenset()), ambient_run_id=RunId("ghost-run")
    )
    assert result.run_id is None
    assert result.tier is None
    assert result.review_required is True


# --- candidate / likely are advisory + review-queued ----------------------------


def test_entity_candidate_is_review_required_and_enqueued() -> None:
    """A T4 candidate is review-required, enqueued, and never billing-grade."""
    repo = InMemoryRunRepository()
    _seed_run(repo, "entity-run")
    queue = InMemoryReviewQueue()
    result = _cascade(repo, queue).bind(_outcome())
    assert result.tier is BindingTier.CANDIDATE
    assert result.review_required is True
    assert result.is_billing_grade is False
    pending = queue.list_pending(TENANT_A)
    assert len(pending) == 1
    assert pending[0] is result


def test_entity_ambiguity_halts_and_enqueues_all() -> None:
    """A T4 epsilon-tie halts: unbound (no single run), all tied candidates enqueued."""
    repo = InMemoryRunRepository()
    _seed_run(repo, "a", minute_offset=-60)
    _seed_run(repo, "b", minute_offset=60)
    queue = InMemoryReviewQueue()
    result = _cascade(repo, queue).bind(_outcome())
    assert result.run_id is None  # ambiguous => no single run is bound
    assert result.tier is None
    assert result.review_required is True
    assert {c.run_id for c in result.candidates} == {RunId("a"), RunId("b")}
    assert queue.list_pending(TENANT_A) == [result]


def test_likely_is_review_required_never_billing_grade() -> None:
    """A T5 likely match is review-required, enqueued, and never billing-grade."""
    repo = InMemoryRunRepository()
    # A run outside the entity window so T4 misses, inside the (wider) T5 window.
    repo.upsert(
        TENANT_A,
        make_run(run_id="far-run", started_at=_OCCURRED + timedelta(hours=20),
                 entity_keys=frozenset({("customer_id", "c-1")})),
    )
    queue = InMemoryReviewQueue()
    cascade = Cascade(
        run_repo=repo,
        review_queue=queue,
        judge=StubLlmJudge(0.9),
        entity_window=timedelta(hours=6),
        semantic_window=timedelta(hours=24),
    )
    result = cascade.bind(_outcome())
    assert result.tier is BindingTier.LIKELY
    assert result.review_required is True
    assert result.is_billing_grade is False
    assert queue.list_pending(TENANT_A) == [result]


# --- no match -------------------------------------------------------------------


def test_no_match_is_unbound_and_review_required() -> None:
    """No tier matches => unbound, review-required, enqueued, not billing-grade."""
    repo = InMemoryRunRepository()
    queue = InMemoryReviewQueue()
    result = _cascade(repo, queue).bind(_outcome())
    assert result.run_id is None
    assert result.tier is None
    assert result.review_required is True
    assert result.is_billing_grade is False
    assert queue.list_pending(TENANT_A) == [result]


# --- labeling invariants --------------------------------------------------------


def test_result_is_tenant_scoped_to_the_outcome() -> None:
    """The result carries the outcome's tenant id (structural isolation)."""
    repo = InMemoryRunRepository()
    _seed_run(repo, "run-1")
    result = _cascade(repo, InMemoryReviewQueue()).bind(
        _outcome(), ambient_run_id=RunId("run-1")
    )
    assert result.tenant_id == TENANT_A


def test_candidate_likely_outcomes_always_review_required() -> None:
    """Every non-deterministic bind is review-required (the headline invariant)."""
    # candidate
    repo_c = InMemoryRunRepository()
    _seed_run(repo_c, "entity-run")
    res_c = _cascade(repo_c, InMemoryReviewQueue()).bind(_outcome())
    # likely
    repo_l = InMemoryRunRepository()
    repo_l.upsert(
        TENANT_A,
        make_run(run_id="far-run", started_at=_OCCURRED + timedelta(hours=20),
                 entity_keys=frozenset({("customer_id", "c-1")})),
    )
    cascade_l = Cascade(
        run_repo=repo_l,
        review_queue=InMemoryReviewQueue(),
        judge=StubLlmJudge(0.9),
        entity_window=timedelta(hours=6),
        semantic_window=timedelta(hours=24),
    )
    res_l = cascade_l.bind(_outcome())
    assert res_c.review_required is True
    assert res_l.review_required is True
    assert res_c.is_billing_grade is False
    assert res_l.is_billing_grade is False
