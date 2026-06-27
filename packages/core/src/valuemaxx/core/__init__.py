"""valuemaxx.core — the typed spine for AI Margin Intelligence.

This package is the single source of truth for every domain type: enums, ids,
the strict pydantic bases, domain event models, rollup helpers, and the
repository ABCs every other package depends on. No other package may redefine a
domain type (enforced by the ``no_type_outside_core`` conformance rule).

The public surface is re-exported explicitly below (no wildcards) so importers
and the JSON-Schema/registry projection have one authoritative list.
"""

from __future__ import annotations

from valuemaxx.core.allocation import AllocatedLine
from valuemaxx.core.attribution import AttributionCandidate, AttributionResult
from valuemaxx.core.base import StrictModel, TenantScopedModel
from valuemaxx.core.cost import CostEvent
from valuemaxx.core.enums import (
    AllocationTier,
    BindingTier,
    CaptureGranularity,
    ConfidenceLabel,
    EvalGrade,
    LabelSource,
    Provenance,
    ReconciliationState,
    SignalClass,
    TokenClass,
)
from valuemaxx.core.errors import (
    AtmError,
    BindingAmbiguityError,
    CaptureError,
    HonestyInvariantError,
    ProvenanceWarning,
    TenantScopeError,
)
from valuemaxx.core.ids import (
    AttemptId,
    AttributionId,
    CorrelationId,
    CostEventId,
    OutcomeEventId,
    ReconciliationRecordId,
    RunId,
    TenantId,
)
from valuemaxx.core.metrics import MetricDefinition
from valuemaxx.core.outcome import OutcomeBinding, OutcomeEvent
from valuemaxx.core.provenance import ProvenanceLabel
from valuemaxx.core.reconciliation import ReconciliationRecord
from valuemaxx.core.repositories import (
    AllocationRepository,
    AttributionResultRepository,
    CostEventRepository,
    OutcomeEventRepository,
    RawRecordRepository,
    ReconciliationRepository,
    RunRepository,
)
from valuemaxx.core.rollup import RollupConfidence, RunCostRollup, compose_label
from valuemaxx.core.run import Run
from valuemaxx.core.tokens import TokenVector

__all__ = [
    "AllocatedLine",
    "AllocationRepository",
    "AllocationTier",
    "AtmError",
    "AttemptId",
    "AttributionCandidate",
    "AttributionId",
    "AttributionResult",
    "AttributionResultRepository",
    "BindingAmbiguityError",
    "BindingTier",
    "CaptureError",
    "CaptureGranularity",
    "ConfidenceLabel",
    "CorrelationId",
    "CostEvent",
    "CostEventId",
    "CostEventRepository",
    "EvalGrade",
    "HonestyInvariantError",
    "LabelSource",
    "MetricDefinition",
    "OutcomeBinding",
    "OutcomeEvent",
    "OutcomeEventId",
    "OutcomeEventRepository",
    "Provenance",
    "ProvenanceLabel",
    "ProvenanceWarning",
    "RawRecordRepository",
    "ReconciliationRecord",
    "ReconciliationRecordId",
    "ReconciliationRepository",
    "ReconciliationState",
    "RollupConfidence",
    "Run",
    "RunCostRollup",
    "RunId",
    "RunRepository",
    "SignalClass",
    "StrictModel",
    "TenantId",
    "TenantScopeError",
    "TenantScopedModel",
    "TokenClass",
    "TokenVector",
    "compose_label",
]
