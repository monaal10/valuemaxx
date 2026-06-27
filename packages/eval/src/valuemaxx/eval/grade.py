"""GRADE — the ground-truth rungs, honestly labeled, capped at directional (§8.2).

This is the honesty core of the eval funnel. Grading picks the *highest available*
ground-truth rung and **labels which one it used**:

    outcome_label  >  human_labeled  >  validated LLM-judge  >  reference

with the hard rule that ``outcome_label`` is valid ONLY where the output
deterministically reconstructs the outcome (classification / extraction /
deterministic resolution). For everything open-ended the grader drops to a labeled
proxy and the resulting grade is **capped at ``directional``** — judge-agreement is
never silently called "outcome parity". Only ``outcome_label`` and ``human_labeled``
rungs may carry the ``reliable`` grade (the ``grade_cap_invariant``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from valuemaxx.core import EvalGrade, LabelSource
from valuemaxx.eval.errors import GroundTruthUnavailableError, JudgeNotValidatedError

if TYPE_CHECKING:
    from valuemaxx.core import LlmJudge
    from valuemaxx.eval.types import ReconstructibilityValidator, TaskType

# A rung carries the ``reliable`` grade only off these two label sources (§8.2);
# this mirrors the core ``grade_cap_invariant`` so the cap is computed, not assumed.
_RELIABLE_SOURCES = frozenset({LabelSource.OUTCOME_LABEL, LabelSource.HUMAN_LABELED})

# Judge/reference parity cutoff: a score >= this counts as "at parity".
_PARITY_CUTOFF = 0.5


@dataclass(frozen=True, slots=True)
class GradeInputs:
    """Everything the grader needs to grade one case against one candidate.

    A frozen dataclass (eval-local working type). The boolean availability flags
    (``has_outcome_labels`` / ``has_human_labels`` / ``judge_validated``) drive rung
    selection; the predictions and rubric drive the actual pass/fail.
    """

    case_id: str
    candidate_model: str
    incumbent_prediction: str
    candidate_prediction: str
    task_type: TaskType
    has_outcome_labels: bool
    has_human_labels: bool
    judge_validated: bool
    rubric: str
    cohort: str = field(default="default")


@dataclass(frozen=True, slots=True)
class CaseGrade:
    """The graded result of one case — carrying the rung used and its capped grade.

    ``label_source`` and ``grade`` let the report label the recommendation honestly:
    a ``directional`` grade off a judge rung is never presented as outcome parity.
    """

    case_id: str
    candidate_model: str
    passed: bool
    label_source: LabelSource
    grade: EvalGrade
    incumbent_prediction: str
    candidate_prediction: str
    cohort: str = field(default="default")


def select_label_source(
    inputs: GradeInputs, *, validator: ReconstructibilityValidator
) -> LabelSource:
    """Choose the highest available, honestly-labeled ground-truth rung (§8.2).

    ``outcome_label`` is chosen ONLY when the task's output is reconstructible AND
    outcome labels are present; otherwise the grader falls to human-labeled, then a
    validated judge, then reference. The reconstructibility check is the single
    honesty gate — an open-ended task never reaches the outcome rung, even with
    labels present.
    """
    reconstructible = validator.is_outcome_reconstructible_from_output(inputs.task_type)
    if reconstructible and inputs.has_outcome_labels:
        return LabelSource.OUTCOME_LABEL
    if inputs.has_human_labels:
        return LabelSource.HUMAN_LABELED
    if inputs.judge_validated:
        return LabelSource.LLM_JUDGE
    return LabelSource.REFERENCE


def grade_for_label_source(label_source: LabelSource) -> EvalGrade:
    """Return the capped grade for a rung — reliable only off outcome/human (§8.2)."""
    return EvalGrade.RELIABLE if label_source in _RELIABLE_SOURCES else EvalGrade.DIRECTIONAL


def grade_case(
    inputs: GradeInputs,
    *,
    validator: ReconstructibilityValidator,
    judge: LlmJudge | None,
    human_verdict: bool | None = None,
) -> CaseGrade:
    """Grade one case on the highest available rung, returning the rung + capped grade.

    - ``outcome_label`` (reconstructible task): pass iff the candidate output equals
      the incumbent reference — answerable from the output alone, no judge.
    - ``human_labeled``: uses the supplied ``human_verdict`` (the gold rung); if none
      is supplied the rung is unavailable and it raises rather than silently passing.
    - ``llm_judge`` / ``reference``: scored by the injected judge against the rubric;
      a judge rung with no ``judge`` is a hard :class:`JudgeNotValidatedError`.

    Args:
        inputs: the case + availability flags.
        validator: the reconstructibility seam (the §8.2 honesty gate).
        judge: the injected LLM judge (required for the judge/reference rungs).
        human_verdict: the human pass/fail (required for the human rung).

    Raises:
        JudgeNotValidatedError: a judge/reference rung was selected but no judge supplied.
        GroundTruthUnavailableError: a human rung was selected but no verdict supplied.
    """
    label_source = select_label_source(inputs, validator=validator)
    grade = grade_for_label_source(label_source)
    passed = _passed_for(inputs, label_source, judge=judge, human_verdict=human_verdict)
    return CaseGrade(
        case_id=inputs.case_id,
        candidate_model=inputs.candidate_model,
        passed=passed,
        label_source=label_source,
        grade=grade,
        incumbent_prediction=inputs.incumbent_prediction,
        candidate_prediction=inputs.candidate_prediction,
        cohort=inputs.cohort,
    )


def _passed_for(
    inputs: GradeInputs,
    label_source: LabelSource,
    *,
    judge: LlmJudge | None,
    human_verdict: bool | None,
) -> bool:
    """Compute pass/fail for the selected rung, raising if its scorer is missing."""
    if label_source is LabelSource.OUTCOME_LABEL:
        # Reconstructible: the output alone answers parity (deterministic).
        return inputs.candidate_prediction == inputs.incumbent_prediction
    if label_source is LabelSource.HUMAN_LABELED:
        if human_verdict is None:
            raise GroundTruthUnavailableError(
                f"human-labeled rung selected for case {inputs.case_id!r} but no "
                "human verdict was supplied"
            )
        return human_verdict
    # llm_judge / reference rungs both require the injected judge.
    if judge is None:
        raise JudgeNotValidatedError(
            f"a {label_source.value} rung was selected for case {inputs.case_id!r} "
            "but no judge was supplied to score it"
        )
    score = judge.grade(
        prediction=inputs.candidate_prediction,
        reference=inputs.incumbent_prediction,
        rubric=inputs.rubric,
    )
    return score >= _PARITY_CUTOFF


__all__ = [
    "CaseGrade",
    "GradeInputs",
    "grade_case",
    "grade_for_label_source",
    "select_label_source",
]
