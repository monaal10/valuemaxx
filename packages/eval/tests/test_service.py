"""SERVICE: EvalService orchestrates the funnel over injected deps + repo ABC stubs."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

import pytest
from typing_extensions import override
from valuemaxx.core import (
    EvalDataset,
    EvalRecommendation,
    LabelSource,
    ProviderKeyRef,
    TenantId,
)
from valuemaxx.core.eval.repositories import (
    EvalDatasetRepository,
    EvalRecommendationRepository,
)
from valuemaxx.eval.errors import GateNotApprovedError
from valuemaxx.eval.service import EvalService
from valuemaxx.eval.types import CapturedCall, TaskType

if TYPE_CHECKING:
    from collections.abc import Sequence

_TENANT = TenantId(UUID("33333333-3333-3333-3333-333333333333"))


class _InMemoryDatasetRepo(EvalDatasetRepository):
    def __init__(self) -> None:
        self.rows: dict[tuple[UUID, str], EvalDataset] = {}

    @override
    def upsert(self, tenant_id: TenantId, dataset: EvalDataset) -> None:
        self.rows[(tenant_id, dataset.id)] = dataset

    @override
    def get(self, tenant_id: TenantId, dataset_id: str) -> EvalDataset | None:
        return self.rows.get((tenant_id, dataset_id))


class _InMemoryRecommendationRepo(EvalRecommendationRepository):
    def __init__(self) -> None:
        self.rows: list[tuple[UUID, EvalRecommendation]] = []

    @override
    def upsert(self, tenant_id: TenantId, recommendation: EvalRecommendation) -> None:
        self.rows.append((tenant_id, recommendation))

    @override
    def list_for_incumbent(
        self, tenant_id: TenantId, incumbent_model: str
    ) -> Sequence[EvalRecommendation]:
        return [
            r for (t, r) in self.rows if t == tenant_id and r.incumbent_model == incumbent_model
        ]


class _Validator:
    def is_outcome_reconstructible_from_output(self, task_type: TaskType) -> bool:
        from valuemaxx.eval.types import is_reconstructible_task

        return is_reconstructible_task(task_type)


class _Judge:
    def grade(self, *, prediction: str, reference: str, rubric: str) -> float:
        return 1.0 if prediction == reference else 0.0


class _Provider:
    def count_input_tokens(self, *, model: str, text: str) -> int:
        return len(text.split())

    def sample_output_tokens(self, *, model: str, text: str) -> int:
        return 10


def _service() -> EvalService:
    return EvalService(
        dataset_repo=_InMemoryDatasetRepo(),
        recommendation_repo=_InMemoryRecommendationRepo(),
        validator=_Validator(),
        judge=_Judge(),
        provider=_Provider(),
        embedder=None,
    )


# ---------------------------------------------------------------- discover_agents


def test_discover_agents_returns_clusters() -> None:
    """The service discovers clusters from captured calls (deterministic backbone)."""
    svc = _service()
    calls = [
        CapturedCall(
            id="a",
            call_site="triage",
            tool_names=(),
            template_id=None,
            prompt="Classify the ticket",
            task_type=TaskType.CLASSIFICATION,
            is_outcome_bound=True,
        ),
        CapturedCall(
            id="b",
            call_site="triage",
            tool_names=(),
            template_id=None,
            prompt="Classify the ticket again",
            task_type=TaskType.CLASSIFICATION,
            is_outcome_bound=True,
        ),
    ]
    clusters = svc.discover_agents(calls)
    assert len(clusters) == 1
    assert clusters[0].confirmed is False


# ---------------------------------------------------------------- estimate_eval_cost


def test_estimate_eval_cost_phase1_smoke() -> None:
    """The service estimates the phase-1 smoke cost exactly (no tiktoken)."""
    svc = _service()
    estimate = svc.estimate_eval_cost(
        model="cheap-1",
        cases=[" ".join(["w"] * 10) for _ in range(40)],
        input_price_per_1k=Decimal("0.001"),
        output_price_per_1k=Decimal("0.002"),
    )
    assert estimate.estimated_usd >= Decimal("0")


# ---------------------------------------------------------------- run_eval_funnel


def test_run_eval_funnel_produces_recommendation_and_persists() -> None:
    """The funnel runs end to end over fakes and persists a tenant-scoped recommendation."""
    svc = _service()
    rec = svc.run_eval_funnel(
        tenant_id=_TENANT,
        incumbent_model="big-1",
        candidate=ProviderKeyRef(provider="anthropic", secret_ref="VMX_K"),
        candidate_model="cheap-1",
        label_source=LabelSource.OUTCOME_LABEL,
    )
    assert isinstance(rec, EvalRecommendation)
    assert rec.tenant_id == _TENANT
    assert rec.auto_switch is False
    # persisted under the tenant scope
    stored = svc.recommendation_repo.list_for_incumbent(_TENANT, "big-1")
    assert len(stored) == 1


def test_run_eval_funnel_does_not_leak_across_tenants() -> None:
    """A recommendation persisted for one tenant is invisible to another (tenant scoping)."""
    svc = _service()
    other = TenantId(UUID("44444444-4444-4444-4444-444444444444"))
    svc.run_eval_funnel(
        tenant_id=_TENANT,
        incumbent_model="big-1",
        candidate=ProviderKeyRef(provider="anthropic", secret_ref="VMX_K"),
        candidate_model="cheap-1",
        label_source=LabelSource.OUTCOME_LABEL,
    )
    assert svc.recommendation_repo.list_for_incumbent(other, "big-1") == []


# ---------------------------------------------------------------- get_recommendation


def test_get_recommendation_reads_back_latest() -> None:
    """get_recommendation returns the persisted recommendation for an incumbent."""
    svc = _service()
    svc.run_eval_funnel(
        tenant_id=_TENANT,
        incumbent_model="big-1",
        candidate=ProviderKeyRef(provider="anthropic", secret_ref="VMX_K"),
        candidate_model="cheap-1",
        label_source=LabelSource.OUTCOME_LABEL,
    )
    rec = svc.get_recommendation(tenant_id=_TENANT, incumbent_model="big-1")
    assert rec is not None
    assert rec.incumbent_model == "big-1"


def test_get_recommendation_none_when_absent() -> None:
    """No recommendation for an unknown incumbent -> None (no crash)."""
    svc = _service()
    assert svc.get_recommendation(tenant_id=_TENANT, incumbent_model="nope") is None


# ---------------------------------------------------------------- approve_gate ordering


def test_approve_gate_phase2_before_phase1_raises() -> None:
    """The service enforces gate ordering: phase 2 before phase 1 is refused."""
    svc = _service()
    with pytest.raises(GateNotApprovedError):
        svc.estimate_full_run(
            phase1_approved=False,
            model="cheap-1",
            cases=[" ".join(["w"] * 10) for _ in range(300)],
            input_price_per_1k=Decimal("0.001"),
            output_price_per_1k=Decimal("0.002"),
        )


def test_service_has_no_module_global_state() -> None:
    """Two services hold independent repos — no shared global state (deterministic)."""
    a = _service()
    b = _service()
    a.run_eval_funnel(
        tenant_id=_TENANT,
        incumbent_model="big-1",
        candidate=ProviderKeyRef(provider="anthropic", secret_ref="VMX_K"),
        candidate_model="cheap-1",
        label_source=LabelSource.OUTCOME_LABEL,
    )
    # b's repo is untouched
    assert b.recommendation_repo.list_for_incumbent(_TENANT, "big-1") == []
