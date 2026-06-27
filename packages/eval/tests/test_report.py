"""REPORT: the diffable recommendation artifact — JSON source of truth, never auto-switch (§8.6)."""

from __future__ import annotations

import json
from decimal import Decimal
from uuid import UUID

from valuemaxx.core import EvalGrade, EvalRecommendation, LabelSource, TenantId
from valuemaxx.eval.grade import CaseGrade
from valuemaxx.eval.report import (
    RecommendationInputs,
    build_recommendation,
    render_markdown,
)
from valuemaxx.eval.search import ParetoPoint
from valuemaxx.eval.stats import Percentiles

_TENANT = TenantId(UUID("22222222-2222-2222-2222-222222222222"))


def _grade(
    cid: str,
    *,
    passed: bool,
    cohort: str = "default",
    label_source: LabelSource = LabelSource.OUTCOME_LABEL,
    inc: str = "ref",
    cand: str = "ref",
) -> CaseGrade:
    reliable = label_source is LabelSource.OUTCOME_LABEL
    return CaseGrade(
        case_id=cid,
        candidate_model="cheap-1",
        passed=passed,
        label_source=label_source,
        grade=EvalGrade.RELIABLE if reliable else EvalGrade.DIRECTIONAL,
        incumbent_prediction=inc,
        candidate_prediction=cand,
        cohort=cohort,
    )


def _inputs(
    *,
    recommended: str | None = "cheap-1",
    grades: list[CaseGrade] | None = None,
    label_source: LabelSource = LabelSource.OUTCOME_LABEL,
) -> RecommendationInputs:
    if grades is None:
        grades = [_grade(f"c{i}", passed=True) for i in range(18)] + [
            _grade(f"c{i}", passed=False) for i in range(18, 20)
        ]
    return RecommendationInputs(
        tenant_id=_TENANT,
        recommended_model=recommended,
        incumbent_model="big-1",
        label_source=label_source,
        graded_cases=grades,
        latency=Percentiles(p50=80.0, p95=180.0, p99=260.0),
        incumbent_monthly_usd=Decimal("1000.00"),
        candidate_monthly_usd=Decimal("250.00"),
        pareto=(
            ParetoPoint(
                model="cheap-1", quality=0.9, cost_usd=2.0, latency_ms_p50=80.0, dominated=False
            ),
            ParetoPoint(
                model="dom", quality=0.5, cost_usd=9.0, latency_ms_p50=300.0, dominated=True
            ),
        ),
        human_label_count=60,
    )


# ---------------------------------------------------------------- build_recommendation


def test_build_returns_core_recommendation() -> None:
    """The artifact is a core EvalRecommendation (no domain type defined here)."""
    rec = build_recommendation(_inputs())
    assert isinstance(rec, EvalRecommendation)
    assert rec.tenant_id == _TENANT
    assert rec.recommended_model == "cheap-1"
    assert rec.incumbent_model == "big-1"


def test_parity_carries_95_ci() -> None:
    """The recommendation carries a 95% CI on the parity (the significance layer §8.6)."""
    rec = build_recommendation(_inputs())
    low, high = rec.parity_ci95
    assert isinstance(low, Decimal)
    assert isinstance(high, Decimal)
    assert Decimal("0") <= low <= high <= Decimal("1")


def test_latency_percentiles_monotone() -> None:
    """Latency p50 <= p95 <= p99 on the artifact."""
    rec = build_recommendation(_inputs())
    assert rec.latency_p50_ms <= rec.latency_p95_ms <= rec.latency_p99_ms


def test_sample_disagreements_present() -> None:
    """Disagreements (where the candidate differed) are recorded — the trust-builder (§8.6)."""
    grades = [
        _grade("agree", passed=True, inc="x", cand="x"),
        _grade("differ", passed=False, inc="x", cand="y"),
    ]
    rec = build_recommendation(_inputs(grades=grades))
    case_ids = {d["case_id"] for d in rec.sample_disagreements}
    assert "differ" in case_ids
    assert "agree" not in case_ids


def test_gap_distribution_per_cohort() -> None:
    """gap_distribution counts failures per cohort across the graded set (§8.6)."""
    grades = [
        _grade("a", passed=False, cohort="enterprise"),
        _grade("b", passed=False, cohort="enterprise"),
        _grade("c", passed=False, cohort="smb"),
        _grade("d", passed=True, cohort="smb"),
    ]
    rec = build_recommendation(_inputs(grades=grades))
    assert rec.gap_distribution["enterprise"] == 2
    assert rec.gap_distribution["smb"] == 1


def test_pareto_dominated_flag_serialized() -> None:
    """The Pareto frontier is serialized with each point's dominated flag (§8.6)."""
    rec = build_recommendation(_inputs())
    dom = {p["model"]: p["dominated"] for p in rec.pareto_frontier}
    assert dom["cheap-1"] is False
    assert dom["dom"] is True


def test_auto_switch_is_false() -> None:
    """The artifact never auto-switches — auto_switch is Literal[False] (§8.6)."""
    rec = build_recommendation(_inputs())
    assert rec.auto_switch is False


def test_grade_reflects_label_source() -> None:
    """A judge-rung recommendation is capped at directional (grade_cap_invariant)."""
    grades = [_grade(f"c{i}", passed=True, label_source=LabelSource.LLM_JUDGE) for i in range(20)]
    rec = build_recommendation(_inputs(label_source=LabelSource.LLM_JUDGE, grades=grades))
    assert rec.label_source is LabelSource.LLM_JUDGE
    assert rec.grade is EvalGrade.DIRECTIONAL


def test_reliable_grade_off_outcome_label() -> None:
    """An outcome-label recommendation may be reliable (the top rung)."""
    rec = build_recommendation(_inputs(label_source=LabelSource.OUTCOME_LABEL))
    assert rec.grade is EvalGrade.RELIABLE


def test_methodology_records_label_source_and_human_count() -> None:
    """The methodology string records the label source and the human-label count (§8.6)."""
    rec = build_recommendation(_inputs(label_source=LabelSource.HUMAN_LABELED))
    assert "human_labeled" in rec.methodology
    assert "60" in rec.methodology


def test_projected_monthly_delta_present() -> None:
    """The methodology records the projected $/month delta at real volume (§8.6)."""
    rec = build_recommendation(_inputs())
    # incumbent 1000 - candidate 250 -> $750/month saving recorded
    assert "750" in rec.methodology


# ---------------------------------------------------------------- render_markdown


def test_markdown_derives_from_json_source_of_truth() -> None:
    """render_markdown derives strictly from the recommendation JSON (source of truth, §8.6)."""
    rec = build_recommendation(_inputs())
    md = render_markdown(rec)
    # values present in the JSON appear in the markdown
    payload = json.loads(rec.model_dump_json())
    assert payload["recommended_model"] in md
    assert payload["incumbent_model"] in md
    assert "auto_switch" in md.lower() or "never auto" in md.lower()


def test_markdown_shows_confidence_grade() -> None:
    """The markdown surfaces the reliable/directional confidence label."""
    judge_grades = [
        _grade(f"c{i}", passed=True, label_source=LabelSource.LLM_JUDGE) for i in range(20)
    ]
    rec = build_recommendation(_inputs(label_source=LabelSource.LLM_JUDGE, grades=judge_grades))
    md = render_markdown(rec)
    assert "directional" in md.lower()


def test_markdown_renders_no_switch_when_recommended_none() -> None:
    """When no model wins, the markdown clearly renders 'no switch' (never a fake win, §8.6)."""
    rec = build_recommendation(_inputs(recommended=None))
    md = render_markdown(rec)
    assert "no switch" in md.lower() or "no recommended" in md.lower()
    assert rec.recommended_model is None


def test_recommendation_json_is_stable_source_of_truth() -> None:
    """The artifact serializes deterministically — the diffable JSON source of truth (§8.6).

    The core EvalRecommendation is strict (tuple fields), so it deliberately does not
    round-trip a JSON *array* back through strict validation; what the report relies
    on is a stable, complete JSON dump that the markdown derives from.
    """
    rec = build_recommendation(_inputs())
    first = rec.model_dump_json()
    second = rec.model_dump_json()
    assert first == second  # deterministic
    payload = json.loads(first)
    # the artifact carries every §8.6 field
    for field in (
        "recommended_model",
        "incumbent_model",
        "grade",
        "label_source",
        "parity_ci95",
        "latency_p50_ms",
        "latency_p95_ms",
        "latency_p99_ms",
        "sample_disagreements",
        "gap_distribution",
        "pareto_frontier",
        "methodology",
        "auto_switch",
    ):
        assert field in payload
    assert payload["auto_switch"] is False
