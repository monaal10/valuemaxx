"""valuemaxx.eval — eval-backed model recommendation (an EVIDENCE layer, §8).

This package is the honest, eval-backed model-recommendation funnel:
``discover -> dataset -> grade -> search -> cost-gate -> recommend -> cadence``.
It is deliberately *not* the product headline — the outcome of an un-run model is
counterfactual, so a recommendation is graded on the best honestly-labeled
ground-truth rung and is **evidence for a human decision, never an auto-switch**.

It depends only on ``valuemaxx.core`` ABCs/Protocols and ``valuemaxx.capabilities``;
it never imports a sibling logic package, a concrete store, a surface framework, or
``tiktoken`` (asserted by conformance rules). All model interaction is through
injected Protocols (``ProviderClient``, ``LlmJudge``, ``Embedder``, ``Clock``,
``Rng``, ``UuidGen``) so the funnel is deterministic and needs no real model.
"""

from __future__ import annotations

from valuemaxx.eval.cadence import should_reeval, surface_switch_if_warranted
from valuemaxx.eval.capabilities import (
    EvalNotWiredError,
    bind_runtime,
    register,
)
from valuemaxx.eval.costgate import (
    Phase1Approval,
    Phase2Approval,
    ProviderTokenizer,
    estimate_full_run_cost,
    estimate_smoke_cost,
    make_phase1_approval,
    make_phase2_approval,
    resolve_provider_key,
)
from valuemaxx.eval.dataset import (
    JudgeValidationResult,
    TraceRecord,
    build_dataset,
    load_committed_human_labels,
    reference_output_of,
    stratum_of,
    validate_judge,
)
from valuemaxx.eval.discover import (
    detect_task_type,
    discover_clusters,
    tool_set_fingerprint,
)
from valuemaxx.eval.drain import skeleton_hash, templatize
from valuemaxx.eval.errors import (
    BudgetExceededError,
    EvalError,
    GateNotApprovedError,
    GroundTruthUnavailableError,
    JudgeNotValidatedError,
)
from valuemaxx.eval.grade import (
    CaseGrade,
    GradeInputs,
    grade_case,
    grade_for_label_source,
    select_label_source,
)
from valuemaxx.eval.report import (
    RecommendationInputs,
    build_recommendation,
    render_markdown,
)
from valuemaxx.eval.search import (
    CandidateScore,
    ParetoPoint,
    confirmation_eval,
    fully_loaded_oss_cost,
    pareto_frontier,
    pick_winner,
    smoke_eval,
)
from valuemaxx.eval.service import EvalService
from valuemaxx.eval.types import (
    CadenceTrigger,
    CapturedCall,
    ClusterCandidate,
    GradedCase,
    HumanLabel,
    JudgeValidation,
    ReconstructibilityValidator,
    Stratum,
    TaskType,
    is_reconstructible_task,
)

__all__ = [
    "BudgetExceededError",
    "CadenceTrigger",
    "CandidateScore",
    "CapturedCall",
    "CaseGrade",
    "ClusterCandidate",
    "EvalError",
    "EvalNotWiredError",
    "EvalService",
    "GateNotApprovedError",
    "GradeInputs",
    "GradedCase",
    "GroundTruthUnavailableError",
    "HumanLabel",
    "JudgeNotValidatedError",
    "JudgeValidation",
    "JudgeValidationResult",
    "ParetoPoint",
    "Phase1Approval",
    "Phase2Approval",
    "ProviderTokenizer",
    "RecommendationInputs",
    "ReconstructibilityValidator",
    "Stratum",
    "TaskType",
    "TraceRecord",
    "bind_runtime",
    "build_dataset",
    "build_recommendation",
    "confirmation_eval",
    "detect_task_type",
    "discover_clusters",
    "estimate_full_run_cost",
    "estimate_smoke_cost",
    "fully_loaded_oss_cost",
    "grade_case",
    "grade_for_label_source",
    "is_reconstructible_task",
    "load_committed_human_labels",
    "make_phase1_approval",
    "make_phase2_approval",
    "pareto_frontier",
    "pick_winner",
    "reference_output_of",
    "register",
    "render_markdown",
    "resolve_provider_key",
    "select_label_source",
    "should_reeval",
    "skeleton_hash",
    "smoke_eval",
    "stratum_of",
    "surface_switch_if_warranted",
    "templatize",
    "tool_set_fingerprint",
    "validate_judge",
]
