"""Real captured cases — and the honesty flags they are allowed to claim.

The funnel used to grade a hardcoded 20-case sample while asserting
``has_outcome_labels=True`` / ``has_human_labels=True``. Those flags select the
evidence rung, and the rung caps the grade, so EVERY run came back ``reliable``
regardless of what ground truth existed. These tests pin the two halves of the fix:
cases come from recorded outcomes, and the flags are derived from what is actually
there — never asserted.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from valuemaxx.core.enums import BindingTier, SignalClass
from valuemaxx.core.ids import OutcomeEventId, RunId, TenantId
from valuemaxx.core.outcome import OutcomeBinding, OutcomeEvent
from valuemaxx.eval.cases import DEFAULT_MAX_CASES, build_case_set

_TENANT = TenantId(UUID("6f1c3b2a-0000-4a00-8000-000000000001"))


def _outcome(n: int, *, bound: bool = True, with_output: bool = True) -> OutcomeEvent:
    raw: dict[str, object] = (
        {"incumbent_output": "resolved", "candidate_output": "resolved"} if with_output else {}
    )
    return OutcomeEvent(
        tenant_id=_TENANT,
        id=OutcomeEventId(f"oe_{n:032d}"),
        name="alt_created",
        signal_class=SignalClass.OUTCOME_CONFIRMED,
        value=None,
        occurred_at=datetime(2026, 7, 30, 12, 0, tzinfo=UTC),
        binding=OutcomeBinding(
            run_id=RunId(f"run-{n}") if bound else None,
            tier=BindingTier.EXACT if bound else None,
            bound_by="AmbientContextResolver" if bound else None,
        ),
        entity_keys=frozenset(),
        correlation_id=None,
        source="test",
        raw=raw,
    )


def test_builds_cases_from_bound_outcomes_with_output() -> None:
    result = build_case_set([_outcome(1), _outcome(2)])
    assert len(result.cases) == 2
    assert result.cases[0][1] == "resolved"


def test_never_claims_human_labels() -> None:
    """No human reviewed these. Claiming it would promote the grade on invented evidence."""
    result = build_case_set([_outcome(1)])
    assert result.has_outcome_labels is True
    assert result.has_human_labels is False


def test_unbound_outcomes_produce_no_cases_and_say_why() -> None:
    """An unbound outcome cannot be attributed to the work that produced it."""
    result = build_case_set([_outcome(1, bound=False)])
    assert result.is_empty
    assert result.has_outcome_labels is False
    assert result.reason is not None
    assert "bound" in result.reason


def test_bound_outcomes_without_output_report_the_content_gap() -> None:
    """Content capture is off by default — say so instead of fabricating cases."""
    result = build_case_set([_outcome(1, with_output=False)])
    assert result.is_empty
    assert result.reason is not None
    assert "captureContent" in result.reason


def test_case_count_is_capped_so_a_run_stays_affordable() -> None:
    """Each case spends real tokens; the operator approving the gate needs a bound."""
    result = build_case_set([_outcome(i) for i in range(DEFAULT_MAX_CASES + 25)])
    assert len(result.cases) == DEFAULT_MAX_CASES


def test_empty_input_is_not_an_error() -> None:
    result = build_case_set([])
    assert result.is_empty
    assert result.reason is not None


def test_empty_case_set_must_not_lend_its_labels_to_fallback_cases() -> None:
    """A bound-but-textless case set reports outcome labels — for cases it does NOT have.

    `build_case_set` returns `has_outcome_labels=True` when bound outcomes exist but
    carry no comparable output, because the labels genuinely exist even though the text
    does not. The funnel must therefore check `is_empty` BEFORE adopting those flags:
    otherwise it grades the fabricated fallback cases while claiming they are
    outcome-labelled, and the recommendation reads `reliable` off invented data.
    """
    result = build_case_set([_outcome(1, with_output=False)])
    assert result.is_empty
    assert result.has_outcome_labels is True  # true of the outcomes, not of any case
