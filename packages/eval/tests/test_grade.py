"""GRADE: the ground-truth rungs — honestly labeled, grade capped at directional (§8.2)."""

from __future__ import annotations

import pytest
from valuemaxx.core import EvalGrade, LabelSource
from valuemaxx.eval.errors import GroundTruthUnavailableError, JudgeNotValidatedError
from valuemaxx.eval.grade import (
    GradeInputs,
    grade_case,
    grade_for_label_source,
    select_label_source,
)
from valuemaxx.eval.types import TaskType


class _StructuralValidator:
    """The default reconstructibility validator (structural task-type rule)."""

    def is_outcome_reconstructible_from_output(self, task_type: TaskType) -> bool:
        from valuemaxx.eval.types import is_reconstructible_task

        return is_reconstructible_task(task_type)


class _FixedJudge:
    """A deterministic judge returning a fixed score (no real model)."""

    def __init__(self, score: float) -> None:
        self._score = score

    def grade(self, *, prediction: str, reference: str, rubric: str) -> float:
        return self._score


def _inputs(
    *,
    task_type: TaskType,
    has_outcome_labels: bool,
    has_human_labels: bool,
    judge_validated: bool,
) -> GradeInputs:
    return GradeInputs(
        case_id="c1",
        candidate_model="cheap-1",
        incumbent_prediction="ref",
        candidate_prediction="cand",
        task_type=task_type,
        has_outcome_labels=has_outcome_labels,
        has_human_labels=has_human_labels,
        judge_validated=judge_validated,
        rubric="is the candidate at parity with the reference?",
    )


# ---------------------------------------------------------------- select_label_source


def test_outcome_label_chosen_when_reconstructible_and_labeled() -> None:
    """A reconstructible task with outcome labels uses the outcome_label rung (§8.2)."""
    source = select_label_source(
        _inputs(
            task_type=TaskType.CLASSIFICATION,
            has_outcome_labels=True,
            has_human_labels=True,
            judge_validated=True,
        ),
        validator=_StructuralValidator(),
    )
    assert source is LabelSource.OUTCOME_LABEL


def test_outcome_label_rejected_for_open_ended_even_with_labels() -> None:
    """THE HONESTY TEST: open-ended never uses outcome_label, even if labels exist (§8.2).

    The output does not reconstruct the outcome, so it falls to a labeled proxy.
    """
    source = select_label_source(
        _inputs(
            task_type=TaskType.OPEN_ENDED,
            has_outcome_labels=True,  # labels present, but task is not reconstructible
            has_human_labels=True,
            judge_validated=True,
        ),
        validator=_StructuralValidator(),
    )
    assert source is not LabelSource.OUTCOME_LABEL
    assert source is LabelSource.HUMAN_LABELED


def test_falls_to_human_when_no_outcome_label() -> None:
    """No outcome label (or non-reconstructible) -> human-labeled rung if available."""
    source = select_label_source(
        _inputs(
            task_type=TaskType.SUMMARIZATION,
            has_outcome_labels=False,
            has_human_labels=True,
            judge_validated=True,
        ),
        validator=_StructuralValidator(),
    )
    assert source is LabelSource.HUMAN_LABELED


def test_falls_to_validated_judge_when_no_human() -> None:
    """No human labels -> a validated judge rung."""
    source = select_label_source(
        _inputs(
            task_type=TaskType.OPEN_ENDED,
            has_outcome_labels=False,
            has_human_labels=False,
            judge_validated=True,
        ),
        validator=_StructuralValidator(),
    )
    assert source is LabelSource.LLM_JUDGE


def test_falls_to_reference_when_judge_unvalidated() -> None:
    """No human and an unvalidated judge -> the reference rung (pre-filter only)."""
    source = select_label_source(
        _inputs(
            task_type=TaskType.OPEN_ENDED,
            has_outcome_labels=False,
            has_human_labels=False,
            judge_validated=False,
        ),
        validator=_StructuralValidator(),
    )
    assert source is LabelSource.REFERENCE


# ---------------------------------------------------------------- grade_for_label_source


def test_grade_cap_outcome_label_is_reliable() -> None:
    """outcome_label -> reliable (the top rung)."""
    assert grade_for_label_source(LabelSource.OUTCOME_LABEL) is EvalGrade.RELIABLE


def test_grade_cap_human_labeled_is_reliable() -> None:
    """human_labeled -> reliable (the second rung)."""
    assert grade_for_label_source(LabelSource.HUMAN_LABELED) is EvalGrade.RELIABLE


def test_grade_cap_judge_is_directional() -> None:
    """validated judge -> capped at directional (judge agreement is not outcome parity)."""
    assert grade_for_label_source(LabelSource.LLM_JUDGE) is EvalGrade.DIRECTIONAL


def test_grade_cap_reference_is_directional() -> None:
    """reference -> capped at directional (pre-filter only)."""
    assert grade_for_label_source(LabelSource.REFERENCE) is EvalGrade.DIRECTIONAL


# ---------------------------------------------------------------- grade_case


def test_grade_case_outcome_label_passes_on_match() -> None:
    """On a reconstructible task, the candidate passes iff its output matches the reference."""
    graded = grade_case(
        GradeInputs(
            case_id="c1",
            candidate_model="cheap-1",
            incumbent_prediction="spam",
            candidate_prediction="spam",
            task_type=TaskType.CLASSIFICATION,
            has_outcome_labels=True,
            has_human_labels=True,
            judge_validated=True,
            rubric="parity?",
        ),
        validator=_StructuralValidator(),
        judge=None,
    )
    assert graded.passed is True
    assert graded.candidate_model == "cheap-1"


def test_grade_case_outcome_label_fails_on_mismatch() -> None:
    """A reconstructible-task mismatch fails — no judge needed."""
    graded = grade_case(
        GradeInputs(
            case_id="c1",
            candidate_model="cheap-1",
            incumbent_prediction="spam",
            candidate_prediction="ham",
            task_type=TaskType.CLASSIFICATION,
            has_outcome_labels=True,
            has_human_labels=False,
            judge_validated=True,
            rubric="parity?",
        ),
        validator=_StructuralValidator(),
        judge=None,
    )
    assert graded.passed is False


def test_grade_case_reference_uses_judge() -> None:
    """The reference rung uses the judge to score parity (the only available scorer)."""
    graded = grade_case(
        _inputs(
            task_type=TaskType.OPEN_ENDED,
            has_outcome_labels=False,
            has_human_labels=False,
            judge_validated=False,  # reference rung
        ),
        validator=_StructuralValidator(),
        judge=_FixedJudge(0.9),
    )
    assert graded.passed is True  # 0.9 >= 0.5 pass cutoff


def test_grade_case_validated_judge_with_judge_none_raises() -> None:
    """Selecting a judge rung but injecting no judge is a hard error (no silent skip)."""
    with pytest.raises(JudgeNotValidatedError, match="judge"):
        grade_case(
            _inputs(
                task_type=TaskType.OPEN_ENDED,
                has_outcome_labels=False,
                has_human_labels=False,
                judge_validated=True,  # judge rung selected...
            ),
            validator=_StructuralValidator(),
            judge=None,  # ...but no judge supplied
        )


def test_grade_case_human_label_with_no_scorer_raises() -> None:
    """A human rung without a human-verdict scorer is unavailable, not silently passed."""
    with pytest.raises(GroundTruthUnavailableError):
        grade_case(
            _inputs(
                task_type=TaskType.SUMMARIZATION,
                has_outcome_labels=False,
                has_human_labels=True,
                judge_validated=False,
            ),
            validator=_StructuralValidator(),
            judge=None,
            human_verdict=None,
        )


def test_grade_case_human_verdict_used_when_present() -> None:
    """A human rung uses the supplied human verdict directly (the gold rung)."""
    graded = grade_case(
        _inputs(
            task_type=TaskType.SUMMARIZATION,
            has_outcome_labels=False,
            has_human_labels=True,
            judge_validated=False,
        ),
        validator=_StructuralValidator(),
        judge=None,
        human_verdict=True,
    )
    assert graded.passed is True


def test_grade_case_records_the_label_source_grade() -> None:
    """grade_case exposes the rung + its capped grade so the report can label honestly."""
    graded = grade_case(
        _inputs(
            task_type=TaskType.OPEN_ENDED,
            has_outcome_labels=False,
            has_human_labels=False,
            judge_validated=True,
        ),
        validator=_StructuralValidator(),
        judge=_FixedJudge(0.8),
    )
    assert graded.label_source is LabelSource.LLM_JUDGE
    assert graded.grade is EvalGrade.DIRECTIONAL
