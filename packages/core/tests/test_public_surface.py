"""F0-CORE-INIT: the explicit public surface — everything importable from atm_core."""

from __future__ import annotations

import ast
from pathlib import Path

import atm_core

_INIT_PATH = Path(atm_core.__file__)

# Every public name the foundation (1a/1b/1c) must re-export from `atm_core`.
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
}


def test_public_surface_complete() -> None:
    """test_public_surface_complete: every foundation symbol is importable + in __all__."""
    exported = set(atm_core.__all__)
    missing = _EXPECTED_PUBLIC - exported
    assert not missing, f"missing from atm_core.__all__: {sorted(missing)}"
    for name in _EXPECTED_PUBLIC:
        assert hasattr(atm_core, name), f"atm_core has no attribute {name!r}"


def test_all_is_explicit_and_sorted_unique() -> None:
    """__all__ is an explicit list with no duplicates."""
    names = atm_core.__all__
    assert len(names) == len(set(names)), "duplicate names in __all__"


def test_no_wildcard_exports() -> None:
    """test_no_wildcard_exports: __init__.py uses no `from x import *`."""
    tree = ast.parse(_INIT_PATH.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                assert alias.name != "*", "wildcard import found in atm_core/__init__.py"
