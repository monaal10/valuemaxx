"""Continuous configuration optimization over observed traffic."""

from valuemaxx.optimization.baseline import RebaselineResult, rebaseline_if_dominant
from valuemaxx.optimization.capabilities import (
    OptimizationNotWiredError,
    bind_runtime,
    register,
)
from valuemaxx.optimization.frontier import (
    ConstraintVerdict,
    FrontierCandidate,
    build_frontier,
    evaluate_constraints,
)
from valuemaxx.optimization.identity import (
    InferredTemplate,
    compute_config_identity,
    infer_system_template,
)
from valuemaxx.optimization.linter import PromptBlock, TrafficCall, lint_traffic
from valuemaxx.optimization.search import (
    STAGES,
    HalvingResult,
    HalvingRound,
    SearchCandidate,
    prefilter_by_cost,
    successive_halving,
)
from valuemaxx.optimization.service import OptimizationService

__all__ = [
    "STAGES",
    "ConstraintVerdict",
    "FrontierCandidate",
    "HalvingResult",
    "HalvingRound",
    "InferredTemplate",
    "OptimizationNotWiredError",
    "OptimizationService",
    "PromptBlock",
    "RebaselineResult",
    "SearchCandidate",
    "TrafficCall",
    "bind_runtime",
    "build_frontier",
    "compute_config_identity",
    "evaluate_constraints",
    "infer_system_template",
    "lint_traffic",
    "prefilter_by_cost",
    "rebaseline_if_dominant",
    "register",
    "successive_halving",
]
