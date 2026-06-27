"""valuemaxx.core — the typed spine for AI Margin Intelligence.

This package is the single source of truth for every domain type: enums, ids,
the strict pydantic bases, domain event models, rollup helpers, and the
repository ABCs every other package depends on. No other package may redefine a
domain type (enforced by the ``no_type_outside_core`` conformance rule).

The public surface is re-exported explicitly below (no wildcards) so importers
and the JSON-Schema/registry projection have one authoritative list.
"""

from __future__ import annotations

from valuemaxx.core.allocation import AllocatedLine, AllocatedRollup
from valuemaxx.core.attribution import AttributionCandidate, AttributionResult
from valuemaxx.core.base import StrictModel, TenantScopedModel
from valuemaxx.core.context import (
    Clock,
    Embedder,
    LlmJudge,
    ProviderClient,
    Rng,
    UuidGen,
    active_run_id,
    run_in_context,
)
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
from valuemaxx.core.eval import (
    CostEstimate,
    CostGatePhase,
    EvalCase,
    EvalDataset,
    EvalDatasetRepository,
    EvalRecommendation,
    EvalRecommendationRepository,
    ModelCandidate,
    ProviderKeyRef,
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
from valuemaxx.core.pricing import PriceBook, PriceCard
from valuemaxx.core.provenance import ProvenanceLabel
from valuemaxx.core.reconciliation import (
    DriftAlert,
    ProvenanceBreakdown,
    ReconciliationRecord,
)
from valuemaxx.core.repositories import (
    AllocationRepository,
    AttributionResultRepository,
    CostEventRepository,
    OutcomeEventRepository,
    RawRecordRepository,
    ReconciliationRepository,
    ReviewQueue,
    RunRepository,
)
from valuemaxx.core.rollup import RollupConfidence, RunCostRollup, compose_label
from valuemaxx.core.run import Run
from valuemaxx.core.tokens import TokenVector
from valuemaxx.core.webhook import (
    OutcomesPredicateValidator,
    SignalClassMapper,
    WebhookResult,
)

__all__ = [
    "AllocatedLine",
    "AllocatedRollup",
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
    "Clock",
    "ConfidenceLabel",
    "CorrelationId",
    "CostEstimate",
    "CostEvent",
    "CostEventId",
    "CostEventRepository",
    "CostGatePhase",
    "DriftAlert",
    "Embedder",
    "EvalCase",
    "EvalDataset",
    "EvalDatasetRepository",
    "EvalGrade",
    "EvalRecommendation",
    "EvalRecommendationRepository",
    "HonestyInvariantError",
    "LabelSource",
    "LlmJudge",
    "MetricDefinition",
    "ModelCandidate",
    "OutcomeBinding",
    "OutcomeEvent",
    "OutcomeEventId",
    "OutcomeEventRepository",
    "OutcomesPredicateValidator",
    "PriceBook",
    "PriceCard",
    "Provenance",
    "ProvenanceBreakdown",
    "ProvenanceLabel",
    "ProvenanceWarning",
    "ProviderClient",
    "ProviderKeyRef",
    "RawRecordRepository",
    "ReconciliationRecord",
    "ReconciliationRecordId",
    "ReconciliationRepository",
    "ReconciliationState",
    "ReviewQueue",
    "Rng",
    "RollupConfidence",
    "Run",
    "RunCostRollup",
    "RunId",
    "RunRepository",
    "SignalClass",
    "SignalClassMapper",
    "StrictModel",
    "TenantId",
    "TenantScopeError",
    "TenantScopedModel",
    "TokenClass",
    "TokenVector",
    "UuidGen",
    "WebhookResult",
    "active_run_id",
    "compose_label",
    "run_in_context",
]
