"""E2E: the full eval funnel over fakes, wired through register -> bind_runtime -> handler."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING
from uuid import UUID

from typing_extensions import override
from valuemaxx.capabilities import Registry
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
from valuemaxx.eval.capabilities import (
    DiscoverAgentsInput,
    GetRecommendationInput,
    RunEvalFunnelInput,
    bind_runtime,
    register,
)
from valuemaxx.eval.service import EvalService

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    import pytest
    from pydantic import BaseModel
    from valuemaxx.eval.types import TaskType

_TENANT = TenantId(UUID("55555555-5555-5555-5555-555555555555"))
SENTINEL_KEY = "SENTINEL_KEY_8f3a"


class _DatasetRepo(EvalDatasetRepository):
    def __init__(self) -> None:
        self.rows: dict[tuple[UUID, str], EvalDataset] = {}

    @override
    def upsert(self, tenant_id: TenantId, dataset: EvalDataset) -> None:
        self.rows[(tenant_id, dataset.id)] = dataset

    @override
    def get(self, tenant_id: TenantId, dataset_id: str) -> EvalDataset | None:
        return self.rows.get((tenant_id, dataset_id))


class _RecRepo(EvalRecommendationRepository):
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


def _wired() -> tuple[Registry, EvalService, _RecRepo]:
    rec_repo = _RecRepo()
    svc = EvalService(
        dataset_repo=_DatasetRepo(),
        recommendation_repo=rec_repo,
        validator=_Validator(),
        judge=_Judge(),
        provider=_Provider(),
        embedder=None,
    )
    reg = Registry()
    register(reg)
    bind_runtime(reg, svc)
    return reg, svc, rec_repo


def _handler(reg: Registry, name: str) -> Callable[[BaseModel], BaseModel]:
    return next(s for s in reg.all() if s.name == name).handler


def test_full_funnel_produces_complete_recommendation() -> None:
    """Running the funnel over fakes yields a complete, honest recommendation artifact."""
    _, svc, _ = _wired()
    rec = svc.run_eval_funnel(
        tenant_id=_TENANT,
        incumbent_model="big-1",
        candidate=ProviderKeyRef(provider="anthropic", secret_ref="ANTHROPIC_API_KEY"),
        candidate_model="cheap-1",
        label_source=LabelSource.OUTCOME_LABEL,
    )
    payload = json.loads(rec.model_dump_json())
    for field in (
        "recommended_model",
        "incumbent_model",
        "grade",
        "label_source",
        "parity_ci95",
        "latency_p50_ms",
        "sample_disagreements",
        "gap_distribution",
        "pareto_frontier",
        "methodology",
        "auto_switch",
    ):
        assert field in payload
    assert payload["auto_switch"] is False


def test_discover_handler_runs_through_registry() -> None:
    """The discover_agents capability handler runs end to end through the registry."""
    reg, _, _ = _wired()
    handler = _handler(reg, "discover_agents")
    out = handler(
        DiscoverAgentsInput(call_sites=("triage", "triage"), prompts=("classify a", "classify b"))
    )
    # both calls share the 'triage' call-site identity -> one cluster
    assert out.model_dump()["cluster_count"] == 1


def test_get_recommendation_handler_reads_back() -> None:
    """After running the funnel, get_recommendation surfaces the persisted artifact."""
    reg, svc, _ = _wired()
    svc.run_eval_funnel(
        tenant_id=_TENANT,
        incumbent_model="big-1",
        candidate=ProviderKeyRef(provider="anthropic", secret_ref="ANTHROPIC_API_KEY"),
        candidate_model="cheap-1",
        label_source=LabelSource.OUTCOME_LABEL,
    )
    handler = _handler(reg, "get_recommendation")
    out = handler(GetRecommendationInput(tenant_id=str(_TENANT), incumbent_model="big-1"))
    dumped = out.model_dump()
    assert dumped["found"] is True
    assert dumped["recommended_model"] == "cheap-1"


def test_run_funnel_handler_is_async_ack() -> None:
    """The run_eval_funnel handler returns an async-job acknowledgement (job id)."""
    reg, _, _ = _wired()
    handler = _handler(reg, "run_eval_funnel")
    out = handler(
        RunEvalFunnelInput(
            tenant_id=str(_TENANT),
            incumbent_model="big-1",
            candidate_model="cheap-1",
            candidate_provider="anthropic",
            candidate_secret_ref="ANTHROPIC_API_KEY",
            label_source="outcome_label",
        )
    )
    dumped = out.model_dump()
    assert dumped["accepted"] is True
    assert dumped["job_id"]


def test_sentinel_key_never_persisted_or_returned(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The provider key (sentinel) is never persisted on the recommendation nor logged.

    The key is resolved from env for the run; the persisted artifact carries only a
    ``secret_ref`` (env var name) via ProviderKeyRef — never the plaintext key.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", SENTINEL_KEY)
    _, svc, rec_repo = _wired()
    with caplog.at_level(logging.DEBUG):
        svc.run_eval_funnel(
            tenant_id=_TENANT,
            incumbent_model="big-1",
            candidate=ProviderKeyRef(provider="anthropic", secret_ref="ANTHROPIC_API_KEY"),
            candidate_model="cheap-1",
            label_source=LabelSource.OUTCOME_LABEL,
        )
    # the sentinel appears in NO persisted recommendation JSON
    for _tenant, rec in rec_repo.rows:
        assert SENTINEL_KEY not in rec.model_dump_json()
    # and in NO log line
    assert SENTINEL_KEY not in caplog.text
