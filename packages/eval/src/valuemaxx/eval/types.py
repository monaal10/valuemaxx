"""Shared eval-local types — enums, frozen dataclasses, and injected Protocols.

These are *working* types local to the eval funnel, deliberately NOT pydantic
domain models: every domain type lives in ``valuemaxx.core`` (the
``no_type_outside_core`` rule), so the eval package's intermediate records are
plain ``StrEnum``/frozen ``dataclass`` values and structural ``Protocol``\\ s.

The honesty line of §8.2 lives here as :func:`is_reconstructible_task`: an
``outcome_label`` rung is valid ONLY where the output deterministically
reconstructs the outcome — classification, extraction, deterministic resolution.
Open-ended / generation tasks are not reconstructible and are graded by a labeled
proxy capped at ``directional``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable


class TaskType(StrEnum):
    """The structurally-detected task type of a discovered agent/prompt cluster (§8.1).

    The first three are *outcome-reconstructible*: the output alone answers "would
    the cheaper model's output also have resolved?". The rest are open-ended and
    must fall to a labeled proxy (§8.2).
    """

    CLASSIFICATION = "classification"
    EXTRACTION = "extraction"
    DETERMINISTIC_RESOLUTION = "deterministic_resolution"
    SUMMARIZATION = "summarization"
    OPEN_ENDED = "open_ended"


_RECONSTRUCTIBLE: frozenset[TaskType] = frozenset(
    {TaskType.CLASSIFICATION, TaskType.EXTRACTION, TaskType.DETERMINISTIC_RESOLUTION}
)


def is_reconstructible_task(task_type: TaskType) -> bool:
    """Whether ``task_type``'s output deterministically reconstructs the outcome (§8.2).

    This is the single honesty gate: ``True`` only for classification / extraction
    / deterministic resolution; ``False`` for everything open-ended.
    """
    return task_type in _RECONSTRUCTIBLE


class Stratum(StrEnum):
    """The four dataset strata for a stratified eval set (§8.3)."""

    FREQUENT = "frequent"
    LONG_TAIL = "long_tail"
    ADVERSARIAL = "adversarial"
    FAILURE = "failure"


class CadenceTrigger(StrEnum):
    """The four re-eval triggers (§8.7) — there is deliberately NO timer/interval.

    Re-evaluation is *triggered*, never on a clock: a new model release, cost
    drift, latency drift, or a newly-discovered agent.
    """

    NEW_MODEL_RELEASE = "new_model_release"
    COST_DRIFT = "cost_drift"
    LATENCY_DRIFT = "latency_drift"
    NEW_AGENT = "new_agent"


@dataclass(frozen=True, slots=True)
class CapturedCall:
    """One captured LLM call, the raw input to discovery (§8.1).

    A frozen dataclass (not a domain model): the eval funnel reads these from the
    joined trace data and clusters them; they are never persisted as a domain type.
    """

    id: str
    call_site: str
    tool_names: tuple[str, ...]
    template_id: str | None
    prompt: str
    task_type: TaskType
    is_outcome_bound: bool
    outcome_label: bool | None = None
    """The captured outcome (resolved/not) — present only on outcome-bound calls."""


@dataclass(frozen=True, slots=True)
class ClusterCandidate:
    """A discovered agent/prompt cluster — always unconfirmed at this layer (§8.1).

    ``confirmed`` is ``False`` because human confirmation of names/merges is the
    onboarding agent's job, out of scope for discovery; discovery only auto-ships
    the cluster boundary, skeleton, and a confidence.
    """

    cluster_id: str
    member_ids: tuple[str, ...]
    skeleton_hash: str
    task_type: TaskType
    confidence: float
    confirmed: bool = False


@dataclass(frozen=True, slots=True)
class JudgeValidation:
    """The result of validating an LLM judge against a committed human-label fixture.

    ``validated`` is ``True`` only when TPR >= 0.9 AND TNR >= 0.9 AND n >= 50 — an
    unvalidated judge caps the recommendation at ``directional`` (§8.2).
    """

    tpr: float
    tnr: float
    n: int
    validated: bool


@dataclass(frozen=True, slots=True)
class HumanLabel:
    """One committed human label for judge validation (the N>=50 fixture row)."""

    case_id: str
    prediction: str
    reference: str
    human_positive: bool
    """The human ground-truth verdict (True = at parity / a pass)."""


@dataclass(frozen=True, slots=True)
class GradedCase:
    """The grade of one eval case against one candidate (§8.2 rungs)."""

    case_id: str
    candidate_model: str
    passed: bool
    incumbent_prediction: str
    candidate_prediction: str
    cohort: str = field(default="default")


@runtime_checkable
class ReconstructibilityValidator(Protocol):
    """Decides whether a task type's output reconstructs the outcome (§8.2).

    The eval-local seam (injected, deterministic) the GRADE step consults before
    it will use the ``outcome_label`` rung. Implementations are typically a thin
    wrapper over :func:`is_reconstructible_task`, but the seam lets a deployment
    override the structural default per task family.
    """

    def is_outcome_reconstructible_from_output(self, task_type: TaskType) -> bool:
        """Return True iff ``task_type``'s output deterministically reconstructs the outcome."""
        ...


__all__ = [
    "CadenceTrigger",
    "CapturedCall",
    "ClusterCandidate",
    "GradedCase",
    "HumanLabel",
    "JudgeValidation",
    "ReconstructibilityValidator",
    "Stratum",
    "TaskType",
    "is_reconstructible_task",
]
