"""G1-CORE-EVAL: eval models — no plaintext key, no auto-switch, grade cap."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal, get_args, get_type_hints
from uuid import uuid4

import pytest
from pydantic import ValidationError
from valuemaxx.core.enums import EvalGrade, LabelSource
from valuemaxx.core.eval import (
    CostEstimate,
    CostGatePhase,
    EvalRecommendation,
    ProviderKeyRef,
)
from valuemaxx.core.ids import TenantId


def _tenant() -> TenantId:
    return TenantId(uuid4())


def _recommendation(grade: EvalGrade, label_source: LabelSource) -> EvalRecommendation:
    return EvalRecommendation(
        tenant_id=_tenant(),
        recommended_model="claude-haiku-4-8",
        incumbent_model="claude-opus-4-8",
        grade=grade,
        label_source=label_source,
        parity_ci95=(Decimal("0.01"), Decimal("0.05")),
        latency_p50_ms=120.0,
        latency_p95_ms=300.0,
        latency_p99_ms=500.0,
        sample_disagreements=(),
        gap_distribution={},
        pareto_frontier=(),
        methodology="pinned snapshots; shared prompt",
    )


def test_auto_switch_is_false_literal() -> None:
    """test_auto_switch_is_false_literal: auto_switch is Literal[False] (True unrepresentable)."""
    hints = get_type_hints(EvalRecommendation)
    auto_switch_hint = hints["auto_switch"]
    assert auto_switch_hint == Literal[False]
    assert get_args(auto_switch_hint) == (False,)
    rec = _recommendation(EvalGrade.DIRECTIONAL, LabelSource.LLM_JUDGE)
    assert rec.auto_switch is False
    # constructing with auto_switch=True is rejected
    with pytest.raises(ValidationError):
        EvalRecommendation(
            tenant_id=_tenant(),
            recommended_model="m",
            incumbent_model="i",
            grade=EvalGrade.DIRECTIONAL,
            label_source=LabelSource.LLM_JUDGE,
            parity_ci95=(Decimal("0"), Decimal("0")),
            latency_p50_ms=1.0,
            latency_p95_ms=1.0,
            latency_p99_ms=1.0,
            sample_disagreements=(),
            gap_distribution={},
            pareto_frontier=(),
            methodology="m",
            auto_switch=True,  # type: ignore[arg-type]
        )


def test_provider_key_ref_has_no_plaintext_field() -> None:
    """test_provider_key_ref_has_no_plaintext_field: only a secret_ref, no plaintext."""
    fields = set(ProviderKeyRef.model_fields)
    forbidden = {"key", "api_key", "secret_value", "plaintext", "value", "token"}
    leaked = fields & forbidden
    assert not leaked, f"ProviderKeyRef exposes plaintext field(s): {leaked}"
    assert "secret_ref" in fields
    ref = ProviderKeyRef(provider="anthropic", secret_ref="ANTHROPIC_API_KEY")
    assert ref.secret_ref == "ANTHROPIC_API_KEY"


def test_reliable_requires_outcome_or_human_label() -> None:
    """test_reliable_requires_outcome_or_human_label: grade_cap_invariant."""
    # RELIABLE is constructible only with outcome_label or human_labeled
    for ok_source in (LabelSource.OUTCOME_LABEL, LabelSource.HUMAN_LABELED):
        rec = _recommendation(EvalGrade.RELIABLE, ok_source)
        assert rec.grade is EvalGrade.RELIABLE
    # RELIABLE off a judge/reference label is rejected
    for bad_source in (LabelSource.LLM_JUDGE, LabelSource.REFERENCE):
        with pytest.raises(ValidationError):
            _recommendation(EvalGrade.RELIABLE, bad_source)


def test_directional_allowed_off_any_label() -> None:
    for source in LabelSource:
        rec = _recommendation(EvalGrade.DIRECTIONAL, source)
        assert rec.grade is EvalGrade.DIRECTIONAL


def test_cost_gate_phase_values() -> None:
    assert {p.value for p in CostGatePhase} == {"smoke", "confirmation"}


def test_cost_estimate_uses_decimal() -> None:
    est = CostEstimate(
        phase=CostGatePhase.SMOKE,
        provider="anthropic",
        model="claude-haiku-4-8",
        estimated_usd=Decimal("1.2345"),
        n_cases=40,
    )
    assert est.estimated_usd == Decimal("1.2345")
