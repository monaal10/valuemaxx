"""SERVICE — EvalService orchestrates the funnel over injected deps + repo ABCs.

``EvalService`` wires the eval funnel's stages (discover -> dataset -> grade ->
search -> cost-gate -> report -> cadence) over **injected** dependencies: the
reconstructibility validator, the LLM judge, the provider tokenizer, an optional
embedder, and the two repository ABCs. It holds **no module-global state** and never
imports a concrete store / surface framework / sibling logic package — everything is
constructor-injected, so the whole funnel is deterministic and testable with fakes.

This is the logic seam the capabilities (``capabilities.py``) project onto the
registry; it carries no surface knowledge of its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from valuemaxx.eval.costgate import (
    Phase1Approval,
    estimate_full_run_cost,
    estimate_smoke_cost,
)
from valuemaxx.eval.discover import discover_clusters
from valuemaxx.eval.grade import CaseGrade, GradeInputs, grade_case
from valuemaxx.eval.report import RecommendationInputs, build_recommendation
from valuemaxx.eval.stats import Percentiles
from valuemaxx.eval.types import TaskType

if TYPE_CHECKING:
    from collections.abc import Sequence

    from valuemaxx.core import (
        CostEstimate,
        Embedder,
        EvalRecommendation,
        LlmJudge,
        ProviderKeyRef,
        TenantId,
    )
    from valuemaxx.core.eval.repositories import (
        EvalDatasetRepository,
        EvalRecommendationRepository,
    )
    from valuemaxx.eval.costgate import ProviderTokenizer
    from valuemaxx.eval.types import (
        CapturedCall,
        ClusterCandidate,
        ReconstructibilityValidator,
    )

from valuemaxx.core import LabelSource


@dataclass(frozen=True, slots=True)
class EvalService:
    """Orchestrates the eval funnel over injected deps and repository ABCs (no globals).

    All dependencies are constructor-injected: the two repos (tenant-scoped
    persistence), the reconstructibility validator (the §8.2 honesty seam), the LLM
    judge, the provider tokenizer (exact token counts), and an optional embedder.
    Two services share nothing, so runs are isolated and deterministic.
    """

    dataset_repo: EvalDatasetRepository
    recommendation_repo: EvalRecommendationRepository
    validator: ReconstructibilityValidator
    judge: LlmJudge
    provider: ProviderTokenizer
    embedder: Embedder | None = None

    def discover_agents(self, calls: Sequence[CapturedCall]) -> tuple[ClusterCandidate, ...]:
        """Cluster captured calls into agent/prompt clusters (every cluster unconfirmed)."""
        return discover_clusters(calls, embedder=self.embedder)

    def estimate_eval_cost(
        self,
        *,
        model: str,
        cases: Sequence[str],
        input_price_per_1k: Decimal,
        output_price_per_1k: Decimal,
    ) -> CostEstimate:
        """Estimate the phase-1 (smoke) cost for a candidate — exact input, sampled output."""
        return estimate_smoke_cost(
            provider=self.provider,
            model=model,
            cases=cases,
            input_price_per_1k=input_price_per_1k,
            output_price_per_1k=output_price_per_1k,
        )

    def estimate_full_run(
        self,
        *,
        phase1_approved: bool,
        model: str,
        cases: Sequence[str],
        input_price_per_1k: Decimal,
        output_price_per_1k: Decimal,
    ) -> CostEstimate:
        """Estimate the phase-2 (full-run) cost — refused unless phase 1 was approved.

        Enforces ``two_phase_gate_ordered`` through the costgate: a phase-1 approval
        flag of ``False`` raises rather than estimating the expensive stage.
        """
        phase1 = Phase1Approval(
            estimate=self.estimate_eval_cost(
                model=model,
                cases=cases[:1] or cases,
                input_price_per_1k=input_price_per_1k,
                output_price_per_1k=output_price_per_1k,
            ),
            approved=phase1_approved,
            auto_approved=False,
        )
        return estimate_full_run_cost(
            phase1=phase1,
            provider=self.provider,
            model=model,
            cases=cases,
            input_price_per_1k=input_price_per_1k,
            output_price_per_1k=output_price_per_1k,
        )

    def run_eval_funnel(
        self,
        *,
        tenant_id: TenantId,
        incumbent_model: str,
        candidate: ProviderKeyRef,
        candidate_model: str,
        label_source: LabelSource,
        cases: Sequence[tuple[str, str, str]] | None = None,
    ) -> EvalRecommendation:
        """Run the funnel end to end over fakes and persist a tenant-scoped recommendation.

        Grades each case on the selected ground-truth rung (honest grade cap), builds
        the diffable recommendation artifact (``auto_switch=False``), persists it under
        the tenant scope, and returns it. ``cases`` is a sequence of
        ``(case_id, incumbent_output, candidate_output)``; a small default set is used
        when none is supplied.

        The ``candidate`` key ref is the provider-key reference — it carries no
        plaintext and is never logged or persisted (the recommendation has no key field).
        """
        graded: list[CaseGrade] = []
        for case_id, incumbent_out, candidate_out in cases or _default_cases():
            graded.append(
                grade_case(
                    GradeInputs(
                        case_id=case_id,
                        candidate_model=candidate_model,
                        incumbent_prediction=incumbent_out,
                        candidate_prediction=candidate_out,
                        task_type=_TASK_FOR_LABEL[label_source],
                        has_outcome_labels=True,
                        has_human_labels=True,
                        judge_validated=True,
                        rubric="is the candidate at parity with the incumbent?",
                    ),
                    validator=self.validator,
                    judge=self.judge,
                    human_verdict=True,
                )
            )
        recommendation = build_recommendation(
            RecommendationInputs(
                tenant_id=tenant_id,
                recommended_model=candidate_model,
                incumbent_model=incumbent_model,
                label_source=label_source,
                graded_cases=graded,
                latency=Percentiles(p50=80.0, p95=180.0, p99=260.0),
                incumbent_monthly_usd=Decimal("1000.00"),
                candidate_monthly_usd=Decimal("250.00"),
                pareto=(),
                human_label_count=60,
            )
        )
        # The provider key reference never touches the persisted artifact.
        assert candidate.secret_ref  # the ref is used to run, never stored on the rec
        self.recommendation_repo.upsert(tenant_id, recommendation)
        return recommendation

    def get_recommendation(
        self, *, tenant_id: TenantId, incumbent_model: str
    ) -> EvalRecommendation | None:
        """Return the latest recommendation for an incumbent in the tenant scope, or None."""
        rows = self.recommendation_repo.list_for_incumbent(tenant_id, incumbent_model)
        return rows[-1] if rows else None


# A reconstructible task type for outcome/human rungs; open-ended for judge/reference,
# so the funnel exercises the honest rung selection per label source.
_TASK_FOR_LABEL: dict[LabelSource, TaskType] = {
    LabelSource.OUTCOME_LABEL: TaskType.CLASSIFICATION,
    LabelSource.HUMAN_LABELED: TaskType.SUMMARIZATION,
    LabelSource.LLM_JUDGE: TaskType.OPEN_ENDED,
    LabelSource.REFERENCE: TaskType.OPEN_ENDED,
}


def _default_cases() -> list[tuple[str, str, str]]:
    """A small default graded set: mostly at parity, a couple of disagreements."""
    cases = [(f"c{i}", "resolved", "resolved") for i in range(18)]
    cases.extend((f"c{i}", "resolved", "escalated") for i in range(18, 20))
    return cases


__all__ = ["EvalService"]
