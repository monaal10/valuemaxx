"""FOUNDATION: shared eval-local types (enums + frozen dataclasses, NOT domain models)."""

from __future__ import annotations

import dataclasses

import pytest
from valuemaxx.eval.types import (
    CadenceTrigger,
    CapturedCall,
    ClusterCandidate,
    JudgeValidation,
    ReconstructibilityValidator,
    Stratum,
    TaskType,
    is_reconstructible_task,
)

# ---------------------------------------------------------------- enums


def test_task_types_split_reconstructible_from_open_ended() -> None:
    """The reconstructible task types are exactly classification/extraction/det-resolution."""
    reconstructible = {t for t in TaskType if is_reconstructible_task(t)}
    assert reconstructible == {
        TaskType.CLASSIFICATION,
        TaskType.EXTRACTION,
        TaskType.DETERMINISTIC_RESOLUTION,
    }


def test_open_ended_is_not_reconstructible() -> None:
    """Open-ended/generation tasks are NOT outcome-reconstructible (the §8.2 honesty line)."""
    assert is_reconstructible_task(TaskType.OPEN_ENDED) is False
    assert is_reconstructible_task(TaskType.SUMMARIZATION) is False


def test_strata_are_the_four_named() -> None:
    """The dataset strata are exactly frequent/long_tail/adversarial/failure (§8.3)."""
    assert {s.value for s in Stratum} == {"frequent", "long_tail", "adversarial", "failure"}


def test_cadence_triggers_are_the_four_named() -> None:
    """The four cadence triggers — NO timer/interval is among them (§8.7)."""
    assert {t.value for t in CadenceTrigger} == {
        "new_model_release",
        "cost_drift",
        "latency_drift",
        "new_agent",
    }


# ---------------------------------------------------------------- frozen dataclasses


def test_captured_call_is_frozen() -> None:
    """CapturedCall is an immutable record (frozen dataclass, not a pydantic model)."""
    call = CapturedCall(
        id="c1",
        call_site="agent.reply",
        tool_names=("search", "lookup"),
        template_id=None,
        prompt="Classify this ticket: order #123 is late",
        task_type=TaskType.CLASSIFICATION,
        is_outcome_bound=True,
    )
    assert dataclasses.is_dataclass(call)
    with pytest.raises(dataclasses.FrozenInstanceError):
        call.id = "c2"  # type: ignore[misc]  # asserting immutability at runtime


def test_cluster_candidate_defaults_unconfirmed() -> None:
    """Every discovered cluster starts unconfirmed (human-confirm is out of scope, §8.1)."""
    cluster = ClusterCandidate(
        cluster_id="grp-1",
        member_ids=("c1", "c2"),
        skeleton_hash="abc123",
        task_type=TaskType.CLASSIFICATION,
        confidence=0.9,
    )
    assert cluster.confirmed is False


def test_judge_validation_record() -> None:
    """JudgeValidation carries tpr/tnr/n and the derived validated flag."""
    v = JudgeValidation(tpr=0.95, tnr=0.92, n=60, validated=True)
    assert v.validated is True
    assert v.n == 60


def test_reconstructibility_validator_is_runtime_checkable() -> None:
    """A structural validator satisfies the eval-local Protocol (injectable, testable)."""

    class _Validator:
        def is_outcome_reconstructible_from_output(self, task_type: TaskType) -> bool:
            return is_reconstructible_task(task_type)

    assert isinstance(_Validator(), ReconstructibilityValidator)
    assert not isinstance(object(), ReconstructibilityValidator)
