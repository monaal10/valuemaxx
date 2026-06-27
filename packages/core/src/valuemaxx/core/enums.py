"""Domain enums — the closed vocabularies of the typed spine.

Every public enum is a :class:`~enum.StrEnum` (serializes as its string value),
never a loose ``str``. The string values are part of the wire/storage contract
and match the design tables exactly; changing one is a breaking change.

The three system honesty axes are :class:`Provenance`, :class:`BindingTier`, and
:class:`SignalClass`. :class:`EvalGrade` and :class:`ReconciliationState` are
deliberately *local/display* concepts — they are NOT honesty axes and must never
ride every event (asserted by tests in core and a G1-EXIT meta-test).
"""

from __future__ import annotations

from enum import StrEnum


class Provenance(StrEnum):
    """Cost-provenance honesty axis (§3.1) — on every cost number.

    ``manual_reconciled`` is the Bedrock/Vertex/Azure CSV-upload reconciliation
    path (§5.3). An ``estimated`` value must never be rendered as billed.
    """

    MEASURED = "measured"
    ESTIMATED = "estimated"
    ALLOCATED = "allocated"
    PROVIDER_RECONCILED = "provider_reconciled"
    MANUAL_RECONCILED = "manual_reconciled"


class BindingTier(StrEnum):
    """Binding-tier honesty axis (§3.1) — on every outcome->run link.

    ``candidate`` and ``likely`` are advisory and review-queued; they are never
    fed to billing-grade metrics.
    """

    EXACT = "exact"
    DETERMINISTIC = "deterministic"
    CANDIDATE = "candidate"
    LIKELY = "likely"


class SignalClass(StrEnum):
    """Outcome signal-class honesty axis (§3.1) — on every outcome event.

    A successful tool call / HTTP 200 is ``action_attempted`` unless the result
    is authoritative. A confirmed outcome may later flip to ``outcome_retracted``
    (removing it from the cost-per-outcome denominator, §3.1 H8).
    """

    ACTION_ATTEMPTED = "action_attempted"
    OUTCOME_CONFIRMED = "outcome_confirmed"
    OUTCOME_RETRACTED = "outcome_retracted"


class CaptureGranularity(StrEnum):
    """Whether a CostEvent represents one HTTP attempt or one public call (§5.2)."""

    PER_ATTEMPT = "per_attempt"
    PER_CALL = "per_call"


class ConfidenceLabel(StrEnum):
    """The single composed user-facing confidence label (§3.1)."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    ADVISORY = "advisory"


class AllocationTier(StrEnum):
    """Shared-COGS allocation tiers (§5.4)."""

    DIRECT = "direct"
    SHARED_PROPORTIONAL = "shared_proportional"
    FIXED_OVERHEAD = "fixed_overhead"


class ReconciliationState(StrEnum):
    """A DISPLAY state on aggregates (§5.3a) — NOT a Provenance value, NOT an axis.

    ``provisional`` / ``estimate_only`` describe a query's reconciliation status;
    they never appear in the :class:`Provenance` vocabulary.
    """

    PROVIDER_RECONCILED = "provider_reconciled"
    PROVISIONAL = "provisional"
    ESTIMATE_ONLY = "estimate_only"


class EvalGrade(StrEnum):
    """Local to the eval package (§8) — a per-recommendation label, NOT an axis."""

    RELIABLE = "reliable"
    DIRECTIONAL = "directional"


class LabelSource(StrEnum):
    """Ground-truth rungs, ranked best-to-worst (§8.2)."""

    OUTCOME_LABEL = "outcome_label"
    HUMAN_LABELED = "human_labeled"
    LLM_JUDGE = "llm_judge"
    REFERENCE = "reference"


class TokenClass(StrEnum):
    """The six token classes (§5.2); the 5m/1h cache writes are DISTINCT fields."""

    INPUT_UNCACHED = "input_uncached"
    CACHE_READ = "cache_read"
    CACHE_WRITE_5M = "cache_write_5m"
    CACHE_WRITE_1H = "cache_write_1h"
    OUTPUT = "output"
    REASONING = "reasoning"


__all__ = [
    "AllocationTier",
    "BindingTier",
    "CaptureGranularity",
    "ConfidenceLabel",
    "EvalGrade",
    "LabelSource",
    "Provenance",
    "ReconciliationState",
    "SignalClass",
    "TokenClass",
]
