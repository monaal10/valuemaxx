"""DATASET: build a stratified eval set from real traces + validate the judge (§8.3)."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING
from uuid import UUID

import pytest
from valuemaxx.core import EvalDataset, LabelSource, TenantId
from valuemaxx.eval.dataset import (
    TraceRecord,
    build_dataset,
    reference_output_of,
    stratum_of,
    validate_judge,
)
from valuemaxx.eval.types import HumanLabel, Stratum

if TYPE_CHECKING:
    from collections.abc import Sequence

_TENANT = TenantId(UUID("11111111-1111-1111-1111-111111111111"))


class _SeededRng:
    """A deterministic Rng over the stdlib random — seeded for reproducible sampling."""

    def __init__(self, seed: int) -> None:
        self._r = random.Random(seed)

    def random(self) -> float:
        return self._r.random()

    def sample(self, population: Sequence[object], k: int) -> Sequence[object]:
        return self._r.sample(list(population), k)


def _trace(
    tid: str,
    *,
    stratum: Stratum,
    outcome_bound: bool = False,
    incumbent_output: str = "out",
) -> TraceRecord:
    return TraceRecord(
        trace_id=tid,
        inputs={"prompt": f"prompt-{tid}"},
        incumbent_output=incumbent_output,
        stratum=stratum,
        is_outcome_bound=outcome_bound,
        outcome_label=True if outcome_bound else None,
        label_source=(LabelSource.OUTCOME_LABEL if outcome_bound else LabelSource.REFERENCE),
    )


def _mixed_traces() -> list[TraceRecord]:
    traces: list[TraceRecord] = []
    for i in range(40):
        traces.append(_trace(f"freq-{i}", stratum=Stratum.FREQUENT))
    for i in range(20):
        traces.append(_trace(f"long-{i}", stratum=Stratum.LONG_TAIL))
    for i in range(15):
        traces.append(_trace(f"adv-{i}", stratum=Stratum.ADVERSARIAL))
    for i in range(15):
        traces.append(_trace(f"fail-{i}", stratum=Stratum.FAILURE))
    for i in range(10):
        traces.append(_trace(f"oc-{i}", stratum=Stratum.FREQUENT, outcome_bound=True))
    return traces


# ---------------------------------------------------------------- build_dataset


def test_build_dataset_returns_core_eval_dataset() -> None:
    """The product is a core EvalDataset (no domain type defined in this package)."""
    ds = build_dataset(
        tenant_id=_TENANT,
        name="support",
        traces=_mixed_traces(),
        target_size=50,
        rng=_SeededRng(7),
    )
    assert isinstance(ds, EvalDataset)
    assert ds.tenant_id == _TENANT


def test_all_four_strata_present() -> None:
    """The stratified set contains all four strata (frequent/long_tail/adversarial/failure)."""
    ds = build_dataset(
        tenant_id=_TENANT, name="s", traces=_mixed_traces(), target_size=50, rng=_SeededRng(1)
    )
    strata = {stratum_of(case) for case in ds.cases}
    assert strata == {Stratum.FREQUENT, Stratum.LONG_TAIL, Stratum.ADVERSARIAL, Stratum.FAILURE}


def test_outcome_bound_oversampled_all_included() -> None:
    """Every outcome-bound trace (all 10) is included before sampling the remainder (§8.3)."""
    ds = build_dataset(
        tenant_id=_TENANT, name="s", traces=_mixed_traces(), target_size=30, rng=_SeededRng(3)
    )
    outcome_case_ids = {c.id for c in ds.cases if c.label_source is LabelSource.OUTCOME_LABEL}
    assert len(outcome_case_ids) == 10


def test_version_increments_from_prior() -> None:
    """Rebuilding with a prior version increments the version (a living artifact)."""
    v1 = build_dataset(
        tenant_id=_TENANT, name="s", traces=_mixed_traces(), target_size=30, rng=_SeededRng(3)
    )
    v2 = build_dataset(
        tenant_id=_TENANT,
        name="s",
        traces=_mixed_traces(),
        target_size=30,
        rng=_SeededRng(3),
        prior_version=v1.version,
    )
    assert v1.version == 1
    assert v2.version == 2


def test_every_case_has_source_trace_id() -> None:
    """Every case back-links to the real trace it was drawn from (§8.3)."""
    ds = build_dataset(
        tenant_id=_TENANT, name="s", traces=_mixed_traces(), target_size=40, rng=_SeededRng(5)
    )
    assert all(c.source_trace_id is not None for c in ds.cases)


def test_reference_output_is_incumbent() -> None:
    """The reference output stored on each case is the incumbent model's output."""
    traces = [_trace("t1", stratum=Stratum.FREQUENT, incumbent_output="INCUMBENT-ANSWER")]
    ds = build_dataset(tenant_id=_TENANT, name="s", traces=traces, target_size=1, rng=_SeededRng(0))
    assert reference_output_of(ds.cases[0]) == "INCUMBENT-ANSWER"


def test_build_dataset_deterministic_with_seeded_rng() -> None:
    """The same seed yields the same case selection (deterministic)."""
    a = build_dataset(
        tenant_id=_TENANT, name="s", traces=_mixed_traces(), target_size=35, rng=_SeededRng(9)
    )
    b = build_dataset(
        tenant_id=_TENANT, name="s", traces=_mixed_traces(), target_size=35, rng=_SeededRng(9)
    )
    assert [c.id for c in a.cases] == [c.id for c in b.cases]


def test_build_dataset_respects_target_size_cap() -> None:
    """The dataset never exceeds the target size (outcome-bound first, then sampled remainder)."""
    ds = build_dataset(
        tenant_id=_TENANT, name="s", traces=_mixed_traces(), target_size=25, rng=_SeededRng(2)
    )
    assert len(ds.cases) <= 25
    # outcome-bound (10) are still all present even under a tight cap
    assert sum(1 for c in ds.cases if c.label_source is LabelSource.OUTCOME_LABEL) == 10


# ---------------------------------------------------------------- validate_judge


def _labels(n: int, *, tpr: float, tnr: float) -> tuple[list[HumanLabel], dict[str, float]]:
    """Build n human labels (half positive, half negative) and a judge-score map.

    The judge scores positives at 1.0 with probability tpr (else 0.0) and negatives
    at 0.0 with probability tnr (else 1.0); scores >= 0.5 are the judge's "pass".
    """
    labels: list[HumanLabel] = []
    scores: dict[str, float] = {}
    half = n // 2
    n_tp = round(tpr * half)
    n_tn = round(tnr * (n - half))
    for i in range(half):  # positives
        cid = f"p{i}"
        labels.append(HumanLabel(case_id=cid, prediction="x", reference="y", human_positive=True))
        scores[cid] = 1.0 if i < n_tp else 0.0
    for i in range(n - half):  # negatives
        cid = f"n{i}"
        labels.append(HumanLabel(case_id=cid, prediction="x", reference="y", human_positive=False))
        scores[cid] = 0.0 if i < n_tn else 1.0
    return labels, scores


def test_validate_judge_passes_at_n50_and_092() -> None:
    """A judge at n=50 with TPR/TNR >= 0.9 validates (reliable usage allowed)."""
    labels, scores = _labels(50, tpr=0.92, tnr=0.92)
    result = validate_judge(labels=labels, judge_scores=scores, threshold=0.5)
    assert result.validated is True
    assert result.n == 50
    assert result.tpr >= 0.9
    assert result.tnr >= 0.9


def test_validate_judge_below_n50_not_validated() -> None:
    """Fewer than 50 human labels never validates, even with perfect agreement."""
    labels, scores = _labels(40, tpr=1.0, tnr=1.0)
    result = validate_judge(labels=labels, judge_scores=scores, threshold=0.5)
    assert result.validated is False


def test_validate_judge_low_tpr_not_validated() -> None:
    """TPR below 0.9 fails validation (the judge misses too many true positives)."""
    labels, scores = _labels(60, tpr=0.7, tnr=0.95)
    result = validate_judge(labels=labels, judge_scores=scores, threshold=0.5)
    assert result.validated is False
    assert result.tpr < 0.9


def test_validate_judge_low_tnr_not_validated() -> None:
    """TNR below 0.9 fails validation (the judge passes too many true negatives)."""
    labels, scores = _labels(60, tpr=0.95, tnr=0.7)
    result = validate_judge(labels=labels, judge_scores=scores, threshold=0.5)
    assert result.validated is False
    assert result.tnr < 0.9


def test_validate_judge_empty_labels_not_validated() -> None:
    """No labels -> not validated (cannot trust an unvalidated judge)."""
    result = validate_judge(labels=[], judge_scores={}, threshold=0.5)
    assert result.validated is False
    assert result.n == 0


def test_committed_human_label_fixture_loads_and_validates() -> None:
    """The shipped N>=50 human-label fixture is present and validates a faithful judge."""
    from valuemaxx.eval.dataset import load_committed_human_labels

    labels = load_committed_human_labels()
    assert len(labels) >= 50
    # a faithful judge: score each label exactly as the human verdict
    scores = {label.case_id: (1.0 if label.human_positive else 0.0) for label in labels}
    result = validate_judge(labels=labels, judge_scores=scores, threshold=0.5)
    assert result.validated is True


def test_validate_judge_missing_score_treated_as_fail() -> None:
    """A label with no judge score is treated as a negative judgement (conservative)."""
    labels, scores = _labels(50, tpr=1.0, tnr=1.0)
    # drop one positive's score -> it becomes a missed true positive
    del scores["p0"]
    result = validate_judge(labels=labels, judge_scores=scores, threshold=0.5)
    assert result.tpr < 1.0


def test_validate_judge_rejects_bad_threshold() -> None:
    """A threshold outside (0, 1) is rejected (closed contract)."""
    labels, scores = _labels(50, tpr=0.92, tnr=0.92)
    with pytest.raises(ValueError, match="threshold"):
        validate_judge(labels=labels, judge_scores=scores, threshold=1.5)
