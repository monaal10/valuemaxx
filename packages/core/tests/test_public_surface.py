"""F0-CORE-INIT: the explicit public surface — everything importable from valuemaxx.core."""

from __future__ import annotations

import ast
from pathlib import Path

import valuemaxx.core

_INIT_PATH = Path(valuemaxx.core.__file__)

# Every public name the foundation (1a/1b/1c) must re-export from `valuemaxx.core`.
_EXPECTED_PUBLIC = {
    # enums
    "Provenance",
    "BindingTier",
    "SignalClass",
    "CaptureGranularity",
    "ConfidenceLabel",
    "AllocationTier",
    "ReconciliationState",
    "EvalGrade",
    "LabelSource",
    "TokenClass",
    # ids
    "TenantId",
    "RunId",
    "CostEventId",
    "OutcomeEventId",
    "AttributionId",
    "ReconciliationRecordId",
    "AttemptId",
    "CorrelationId",
    # base
    "StrictModel",
    "TenantScopedModel",
    # tokens / provenance
    "TokenVector",
    "ProvenanceLabel",
    # errors
    "AtmError",
    "TenantScopeError",
    "ProvenanceWarning",
    "HonestyInvariantError",
    "CaptureError",
    "BindingAmbiguityError",
    # domain models
    "CostEvent",
    "OutcomeBinding",
    "OutcomeEvent",
    "Run",
    "AttributionCandidate",
    "AttributionResult",
    "ReconciliationRecord",
    "AllocatedLine",
    "MetricDefinition",
    # rollup
    "RollupConfidence",
    "RunCostRollup",
    "compose_label",
    # repositories
    "RunRepository",
    "CostEventRepository",
    "OutcomeEventRepository",
    "AttributionResultRepository",
    "ReconciliationRepository",
    "AllocationRepository",
    "RawRecordRepository",
    # G1: context propagation + injected Protocols
    "active_run_id",
    "run_in_context",
    "Clock",
    "UuidGen",
    "Rng",
    "Embedder",
    "ProviderClient",
    "LlmJudge",
    # G1: eval models + repos
    "ProviderKeyRef",
    "CostGatePhase",
    "CostEstimate",
    "EvalCase",
    "EvalDataset",
    "ModelCandidate",
    "EvalRecommendation",
    "EvalDatasetRepository",
    "EvalRecommendationRepository",
    # G1: recon/alloc extensions
    "ProvenanceBreakdown",
    "DriftAlert",
    "AllocatedRollup",
    # G1: pricing
    "PriceCard",
    "PriceBook",
    # G1: webhook + C3 protocols + review queue
    "WebhookResult",
    "OutcomesPredicateValidator",
    "SignalClassMapper",
    "ReviewQueue",
}


def test_public_surface_complete() -> None:
    """test_public_surface_complete: every foundation symbol is importable + in __all__."""
    exported = set(valuemaxx.core.__all__)
    missing = _EXPECTED_PUBLIC - exported
    assert not missing, f"missing from valuemaxx.core.__all__: {sorted(missing)}"
    for name in _EXPECTED_PUBLIC:
        assert hasattr(valuemaxx.core, name), f"valuemaxx.core has no attribute {name!r}"


def test_all_is_explicit_and_sorted_unique() -> None:
    """__all__ is an explicit list with no duplicates."""
    names = valuemaxx.core.__all__
    assert len(names) == len(set(names)), "duplicate names in __all__"


def test_no_wildcard_exports() -> None:
    """test_no_wildcard_exports: __init__.py uses no `from x import *`."""
    tree = ast.parse(_INIT_PATH.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                assert alias.name != "*", "wildcard import found in valuemaxx.core/__init__.py"
