"""REPORT — the diffable recommendation artifact (JSON source of truth + markdown) (§8.6).

The recommendation is **evidence for a human decision, never an auto-switch**. It
is a core :class:`~valuemaxx.core.EvalRecommendation` (the JSON source of truth)
carrying: parity with a **95% CI** (the significance layer Promptfoo/Braintrust
omit), the projected $/month delta at real volume, latency p50/p95/p99, the
**sample disagreements** (where the cheaper model differed — the trust-builder), the
gap distribution across cohorts, the Pareto frontier with dominated points flagged,
the full methodology (label source + human-label count), and the confidence grade
(``reliable``/``directional``, honestly capped by the label source).

:func:`render_markdown` derives the human/PR view **from** the JSON — the JSON is
the single source of truth, so the two never drift. ``auto_switch`` is always
``False`` (``Literal[False]`` in core — ``True`` is unrepresentable).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from valuemaxx.core import EvalRecommendation
from valuemaxx.eval.grade import grade_for_label_source
from valuemaxx.eval.stats import wilson_ci

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from valuemaxx.core import LabelSource, TenantId
    from valuemaxx.eval.grade import CaseGrade
    from valuemaxx.eval.search import ParetoPoint
    from valuemaxx.eval.stats import Percentiles


@dataclass(frozen=True, slots=True)
class RecommendationInputs:
    """Everything the report needs to assemble the recommendation artifact (§8.6).

    A frozen dataclass (eval-local). ``recommended_model`` is ``None`` when no model
    won the search — the artifact then honestly renders "no switch".
    """

    tenant_id: TenantId
    recommended_model: str | None
    incumbent_model: str
    label_source: LabelSource
    graded_cases: Sequence[CaseGrade]
    latency: Percentiles
    incumbent_monthly_usd: Decimal
    candidate_monthly_usd: Decimal
    pareto: Sequence[ParetoPoint]
    human_label_count: int


def build_recommendation(inputs: RecommendationInputs) -> EvalRecommendation:
    """Assemble the diffable recommendation artifact from the graded funnel (§8.6).

    Computes the parity proportion + its 95% Wilson CI, the per-cohort gap
    distribution, the sample disagreements, the serialized Pareto frontier (with the
    dominated flag), and the methodology (label source, human-label count, projected
    monthly delta). The grade is honestly capped by ``inputs.label_source`` so a
    judge/reference rung can never carry ``reliable`` (``grade_cap_invariant``).
    """
    total = len(inputs.graded_cases)
    passes = sum(1 for g in inputs.graded_cases if g.passed)
    low, high = wilson_ci(successes=passes, n=total) if total else (0.0, 0.0)
    parity_ci95 = (_to_money4(low), _to_money4(high))

    grade = grade_for_label_source(inputs.label_source)
    monthly_delta = inputs.incumbent_monthly_usd - inputs.candidate_monthly_usd

    return EvalRecommendation(
        tenant_id=inputs.tenant_id,
        recommended_model=inputs.recommended_model,
        incumbent_model=inputs.incumbent_model,
        grade=grade,
        label_source=inputs.label_source,
        parity_ci95=parity_ci95,
        latency_p50_ms=inputs.latency.p50,
        latency_p95_ms=inputs.latency.p95,
        latency_p99_ms=inputs.latency.p99,
        sample_disagreements=_disagreements(inputs.graded_cases),
        gap_distribution=_gap_distribution(inputs.graded_cases),
        pareto_frontier=_pareto(inputs.pareto),
        methodology=_methodology(
            inputs, parity=passes / total if total else 0.0, delta=monthly_delta
        ),
        auto_switch=False,
    )


def render_markdown(rec: EvalRecommendation) -> str:
    """Render the human/PR markdown view derived FROM the recommendation JSON (§8.6).

    The JSON is the source of truth; this view reads only the artifact's fields, so
    the markdown can never disagree with the JSON. When no model won, it renders a
    clear "no switch" rather than a fake recommendation.
    """
    lines: list[str] = ["# Model recommendation (evidence, not an auto-switch)", ""]
    if rec.recommended_model is None:
        lines.append(f"**No switch recommended** — no candidate beat `{rec.incumbent_model}`.")
    else:
        lines.append(
            f"**Recommended:** `{rec.recommended_model}` vs incumbent `{rec.incumbent_model}`"
        )
    low, high = rec.parity_ci95
    lines.extend(
        [
            "",
            f"- Confidence: **{rec.grade.value}** (label source: `{rec.label_source.value}`)",
            f"- Parity 95% CI: [{low}, {high}]",
            f"- Latency: p50 {rec.latency_p50_ms}ms / p95 {rec.latency_p95_ms}ms / "
            f"p99 {rec.latency_p99_ms}ms",
            f"- Sample disagreements: {len(rec.sample_disagreements)}",
            f"- Gap by cohort: {dict(rec.gap_distribution)}",
            "",
            f"_Methodology:_ {rec.methodology}",
            "",
            f"auto_switch = {rec.auto_switch} — promotion is a human decision "
            "(human -> canary -> auto-rollback), never automatic.",
        ]
    )
    return "\n".join(lines)


def _disagreements(cases: Sequence[CaseGrade]) -> tuple[Mapping[str, object], ...]:
    """The cases where the candidate's output differed from the incumbent's."""
    return tuple(
        {
            "case_id": g.case_id,
            "cohort": g.cohort,
            "incumbent": g.incumbent_prediction,
            "candidate": g.candidate_prediction,
            "passed": g.passed,
        }
        for g in cases
        if g.candidate_prediction != g.incumbent_prediction
    )


def _gap_distribution(cases: Sequence[CaseGrade]) -> dict[str, int]:
    """Failures per cohort across the graded set (where the candidate fell short)."""
    gaps: dict[str, int] = {}
    for g in cases:
        if not g.passed:
            gaps[g.cohort] = gaps.get(g.cohort, 0) + 1
    return gaps


def _pareto(points: Sequence[ParetoPoint]) -> tuple[Mapping[str, object], ...]:
    """Serialize the Pareto frontier with each point's dominated flag."""
    return tuple(
        {
            "model": p.model,
            "quality": p.quality,
            "cost_usd": p.cost_usd,
            "latency_ms_p50": p.latency_ms_p50,
            "dominated": p.dominated,
        }
        for p in points
    )


def _methodology(inputs: RecommendationInputs, *, parity: float, delta: Decimal) -> str:
    """The methodology line: label source, human-label count, parity, projected delta."""
    return (
        f"label_source={inputs.label_source.value}; "
        f"human_labels={inputs.human_label_count}; "
        f"n_cases={len(inputs.graded_cases)}; "
        f"parity={parity:.3f}; "
        f"projected_monthly_delta_usd={delta}"
    )


def _to_money4(value: float) -> Decimal:
    """Quantize a proportion to 4 decimal places as a Decimal (the CI bounds)."""
    return Decimal(str(value)).quantize(Decimal("0.0001"))


__all__ = ["RecommendationInputs", "build_recommendation", "render_markdown"]
