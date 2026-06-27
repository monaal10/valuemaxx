"""F0-CORE-1a: exact enum string values + the honesty-axis identity.

The three honesty axes are Provenance / BindingTier / SignalClass. EvalGrade and
ReconciliationState are deliberately LOCAL/display, never system axes — encoded
here so a future change that promotes them to an axis trips a test.
"""

from __future__ import annotations

from enum import StrEnum

import pytest
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


def test_provenance_values_exact() -> None:
    """T-EN-1: Provenance string values match the design table exactly."""
    assert {p.value for p in Provenance} == {
        "measured",
        "estimated",
        "allocated",
        "provider_reconciled",
        "manual_reconciled",
    }
    # manual_reconciled is the Bedrock/Vertex/Azure CSV-upload path (§5.3).
    assert Provenance.MANUAL_RECONCILED.value == "manual_reconciled"


def test_binding_tier_and_signal_values_exact() -> None:
    """T-EN-2: BindingTier + SignalClass values exact."""
    assert {t.value for t in BindingTier} == {
        "exact",
        "deterministic",
        "candidate",
        "likely",
    }
    assert {s.value for s in SignalClass} == {
        "action_attempted",
        "outcome_confirmed",
        "outcome_retracted",
    }


def test_reconciliation_state_not_a_provenance() -> None:
    """T-EN-3: provisional/estimate_only are display states, not Provenance values."""
    provenance_values = {p.value for p in Provenance}
    assert "provisional" not in provenance_values
    assert "estimate_only" not in provenance_values
    # ReconciliationState carries them as transient display states (§5.3a).
    assert ReconciliationState.PROVISIONAL.value == "provisional"
    assert ReconciliationState.ESTIMATE_ONLY.value == "estimate_only"


def test_eval_grade_and_recon_state_are_not_honesty_axes() -> None:
    """The three honesty axes are exactly Provenance/BindingTier/SignalClass."""
    honesty_axes = (Provenance, BindingTier, SignalClass)
    assert EvalGrade not in honesty_axes
    assert ReconciliationState not in honesty_axes


def test_capture_granularity_values() -> None:
    assert {g.value for g in CaptureGranularity} == {"per_attempt", "per_call"}


def test_confidence_label_values() -> None:
    assert {c.value for c in ConfidenceLabel} == {"high", "medium", "low", "advisory"}


def test_allocation_tier_values() -> None:
    assert {a.value for a in AllocationTier} == {
        "direct",
        "shared_proportional",
        "fixed_overhead",
    }


def test_eval_grade_values() -> None:
    assert {g.value for g in EvalGrade} == {"reliable", "directional"}


def test_label_source_values() -> None:
    assert {ls.value for ls in LabelSource} == {
        "outcome_label",
        "human_labeled",
        "llm_judge",
        "reference",
    }


def test_token_class_values_six() -> None:
    """The six token classes (§5.2): 5m/1h cache writes are DISTINCT."""
    assert {tc.value for tc in TokenClass} == {
        "input_uncached",
        "cache_read",
        "cache_write_5m",
        "cache_write_1h",
        "output",
        "reasoning",
    }


@pytest.mark.parametrize(
    "enum_cls",
    [
        Provenance,
        BindingTier,
        SignalClass,
        CaptureGranularity,
        ConfidenceLabel,
        AllocationTier,
        ReconciliationState,
        EvalGrade,
        LabelSource,
        TokenClass,
    ],
)
def test_all_enums_are_str_enums(enum_cls: type[StrEnum]) -> None:
    """Public enums are StrEnum (serialize as their string value), never loose str."""
    assert issubclass(enum_cls, StrEnum)
    for member in enum_cls:
        assert isinstance(member.value, str)
