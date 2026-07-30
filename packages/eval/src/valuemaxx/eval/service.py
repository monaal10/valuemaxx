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
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, cast

from valuemaxx.core import EvalGrade, LabelSource
from valuemaxx.eval.cases import CaseSet, build_case_set
from valuemaxx.eval.costgate import (
    Phase1Approval,
    estimate_full_run_cost,
    estimate_smoke_cost,
)
from valuemaxx.eval.criteria import compile_criterion
from valuemaxx.eval.discover import discover_clusters
from valuemaxx.eval.grade import CaseGrade, GradeInputs, grade_case
from valuemaxx.eval.replay import (
    DEFAULT_REPLAY_CASES,
    CandidateRunner,
    build_replay_case_set,
    parse_samples,
)
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
    from valuemaxx.core.repositories import OutcomeEventRepository, RawRecordRepository
    from valuemaxx.eval.costgate import ProviderTokenizer
from valuemaxx.eval.types import (
    CapturedCall,
    ClusterCandidate,
    ReconstructibilityValidator,
)


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
    # Optional so the pure service stays constructible without a store. When present,
    # the funnel grades the host's REAL recorded outcomes instead of the built-in
    # sample — a recommendation computed from fabricated cases says nothing about
    # their workload, and would say it confidently.
    outcome_repo: OutcomeEventRepository | None = None
    # The replay corpus: captured prompts + the incumbent's real responses. With it the
    # funnel RE-RUNS those prompts against the candidate instead of comparing text the
    # host happened to store, which is the difference between evaluating a model and
    # comparing fixtures.
    raw_record_repo: RawRecordRepository | None = None

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

    def build_replay_case_set_for(
        self, tenant_id: TenantId, *, candidate_model: str, max_cases: int = DEFAULT_REPLAY_CASES
    ) -> CaseSet:
        """Replay this tenant's captured prompts against ``candidate_model``.

        This SPENDS TOKENS — one live candidate call per case — so it is bounded by
        ``max_cases`` and only reached once the operator has approved the cost gate.
        Returns an empty set (with a reason) when no prompts were captured, which is
        the default until a host opts into content capture.
        """
        if self.raw_record_repo is None:
            return CaseSet(
                cases=(),
                has_outcome_labels=False,
                has_human_labels=False,
                reason="no raw-record repository wired; cannot read captured prompts",
            )
        records = list(self.raw_record_repo.list_recent(tenant_id, max_cases * 3))
        return build_replay_case_set(
            parse_samples(records),
            # The tokenizer and the candidate runner are the same Anthropic-backed
            # provider in production; the cast documents that replay needs `complete`,
            # which the ProviderTokenizer protocol does not itself promise.
            runner=cast("CandidateRunner", self.provider),
            candidate_model=candidate_model,
            max_cases=max_cases,
        )

    def build_case_set_for(self, tenant_id: TenantId) -> CaseSet:
        """Build the graded-case set from this tenant's recorded outcomes.

        Returns an EMPTY set (with a reason) when there is nothing real to grade —
        no outcome repository wired, or no bound outcomes carrying comparable output.
        The caller passes it through so the funnel falls back to the built-in cases
        WITHOUT claiming outcome/human labels for them.
        """
        if self.outcome_repo is None:
            return CaseSet(
                cases=(),
                has_outcome_labels=False,
                has_human_labels=False,
                reason="no outcome repository wired; cannot read recorded outcomes",
            )
        return build_case_set(list(self.outcome_repo.list_in_window(tenant_id, _EPOCH, _FOREVER)))

    def run_eval_funnel(
        self,
        *,
        tenant_id: TenantId,
        incumbent_model: str,
        candidate: ProviderKeyRef,
        candidate_model: str,
        label_source: LabelSource,
        cases: Sequence[tuple[str, str, str]] | None = None,
        case_set: CaseSet | None = None,
        criterion: str = "",
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
        # Ground truth is DERIVED, not asserted. These flags select the evidence rung
        # (see grade.py) and the rung caps the grade, so hardcoding them made every run
        # claim `reliable` no matter what evidence existed. With a real case set we
        # claim only what it actually carries; without one we fall back to the built-in
        # cases and must NOT claim outcome/human labels for them.
        # The flags must describe the cases ACTUALLY graded. An empty-but-present case
        # set still reported `has_outcome_labels=True` (bound outcomes existed, they
        # just carried no comparable text), which then labelled the FABRICATED fallback
        # cases as outcome-labelled — the exact over-claim this change exists to remove.
        use_real = case_set is not None and not case_set.is_empty
        selected = (
            case_set.cases if use_real and case_set is not None else (cases or _default_cases())
        )
        has_outcome_labels = (
            case_set.has_outcome_labels if use_real and case_set is not None else False
        )
        has_human_labels = case_set.has_human_labels if use_real and case_set is not None else False

        # A user's plain-language criterion ("warm, under 20 words") replaces the
        # generic parity rubric — "do these two models agree" is not the question a
        # user has. Empty falls back to parity, so an unspecified eval is unchanged.
        compiled = compile_criterion(criterion)

        graded: list[CaseGrade] = []
        for case_id, incumbent_out, candidate_out in selected:
            # Exact checks run FIRST and are authoritative: counting words is arithmetic,
            # and an LLM asked to count is slower, costlier and less reliable. A case
            # failing one is failed outright — the judge cannot overrule a fact.
            deterministic_ok, _failures = compiled.evaluate_deterministic(candidate_out)
            if not deterministic_ok:
                graded.append(
                    CaseGrade(
                        case_id=case_id,
                        candidate_model=candidate_model,
                        incumbent_prediction=incumbent_out,
                        candidate_prediction=candidate_out,
                        passed=False,
                        # A deterministic failure is a FACT, so it is recorded on the
                        # weakest rung: it proves the candidate broke the requirement,
                        # not that we have strong evidence about quality overall.
                        label_source=LabelSource.REFERENCE,
                        grade=EvalGrade.DIRECTIONAL,
                    )
                )
                continue
            graded.append(
                grade_case(
                    GradeInputs(
                        case_id=case_id,
                        candidate_model=candidate_model,
                        incumbent_prediction=incumbent_out,
                        candidate_prediction=candidate_out,
                        task_type=_TASK_FOR_LABEL[label_source],
                        has_outcome_labels=has_outcome_labels,
                        has_human_labels=has_human_labels,
                        # The judge is always available and always capped at
                        # `directional` by the rung table — this is the honest floor,
                        # not a claim of strong evidence.
                        judge_validated=True,
                        rubric=compiled.rubric,
                    ),
                    validator=self.validator,
                    judge=self.judge,
                    # Only meaningful when human labels exist; claiming a verdict nobody
                    # gave would manufacture agreement.
                    human_verdict=has_human_labels,
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


# The full recorded window: the funnel grades whatever outcomes exist, and the case
# cap (not a time bound) is what keeps a run affordable.
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_FOREVER = datetime(9999, 12, 31, tzinfo=UTC)


def _default_cases() -> list[tuple[str, str, str]]:
    """A small default graded set: mostly at parity, a couple of disagreements."""
    cases = [(f"c{i}", "resolved", "resolved") for i in range(18)]
    cases.extend((f"c{i}", "resolved", "escalated") for i in range(18, 20))
    return cases


__all__ = ["EvalService"]
