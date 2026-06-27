"""DATASET — build a stratified eval set from real traces + validate the judge (§8.3).

The eval set is a *living artifact* built from real captured traces: stratified
across frequent / long-tail / adversarial / failure cohorts, **oversampling the
outcome-bound traces** (all of them are included before the remainder is sampled —
they are the only rung that can earn a ``reliable`` grade, §8.2). Every case
back-links to its ``source_trace_id`` and carries the incumbent model's output as
the reference. Versions increment on rebuild.

The product is a core :class:`~valuemaxx.core.EvalDataset` of core
:class:`~valuemaxx.core.EvalCase`\\ s — no domain type is defined here
(``no_type_outside_core``). Per-case metadata (stratum, reference output,
outcome-bound flag/label) rides in the case ``inputs`` mapping under reserved keys,
read back via :func:`stratum_of` / :func:`reference_output_of`.

:func:`validate_judge` is the EvalGen-inspired human-alignment gate: an LLM judge
is usable only when it agrees with a committed N>=50 human-label fixture at
TPR/TNR >= 0.9; otherwise the recommendation is capped at ``directional`` (§8.2).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from typing import TYPE_CHECKING, cast

from valuemaxx.core import EvalCase, EvalDataset, LabelSource
from valuemaxx.eval.types import HumanLabel, Stratum
from valuemaxx.eval.types import JudgeValidation as JudgeValidationResult

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from valuemaxx.core import Rng, TenantId

# Reserved keys under which per-case metadata rides in EvalCase.inputs (so the
# domain model stays in core, unextended).
_STRATUM_KEY = "_eval_stratum"
_REFERENCE_KEY = "_eval_reference_output"
_OUTCOME_LABEL_KEY = "_eval_outcome_label"

_HUMAN_LABELS_FILE = "human_labels_n50.json"


@dataclass(frozen=True, slots=True)
class TraceRecord:
    """One real captured trace, the raw input to dataset construction (§8.3).

    A frozen dataclass (not a domain model): the joined trace data the eval funnel
    reads. ``incumbent_output`` becomes the case's reference; ``stratum`` and
    ``is_outcome_bound`` drive stratification and oversampling.
    """

    trace_id: str
    inputs: Mapping[str, object]
    incumbent_output: str
    stratum: Stratum
    is_outcome_bound: bool
    outcome_label: bool | None
    label_source: LabelSource


def build_dataset(
    *,
    tenant_id: TenantId,
    name: str,
    traces: Sequence[TraceRecord],
    target_size: int,
    rng: Rng,
    prior_version: int = 0,
) -> EvalDataset:
    """Build a stratified, outcome-oversampled eval dataset from real traces (§8.3).

    Outcome-bound traces are ALL included first (they alone can earn ``reliable``);
    the remaining budget is filled by sampling the rest with the injected ``rng``,
    keeping coverage across all four strata. Sampling is deterministic for a seeded
    rng. The version is ``prior_version + 1`` so the artifact's lineage is explicit.

    Args:
        tenant_id: the owning tenant (structural isolation, §3.2).
        name: the dataset name.
        traces: the real captured traces to draw from.
        target_size: the desired number of cases (a cap; outcome-bound are kept even
            if they alone meet it).
        rng: the injected random source (seeded under test for reproducibility).
        prior_version: the previous version number (0 if this is the first build).

    Returns:
        A core :class:`~valuemaxx.core.EvalDataset` whose cases back-link to traces.
    """
    outcome_bound = [t for t in traces if t.is_outcome_bound]
    remainder = [t for t in traces if not t.is_outcome_bound]

    chosen: list[TraceRecord] = list(outcome_bound)
    budget = max(0, target_size - len(chosen))
    if budget and remainder:
        # Stratify the remainder so every present stratum is represented, then fill.
        chosen.extend(_sample_stratified(remainder, budget, rng))

    cases = tuple(_to_case(t) for t in chosen)
    return EvalDataset(
        tenant_id=tenant_id,
        id=f"{name}-v{prior_version + 1}",
        name=name,
        version=prior_version + 1,
        cases=cases,
    )


def _sample_stratified(
    remainder: Sequence[TraceRecord], budget: int, rng: Rng
) -> list[TraceRecord]:
    """Sample ``budget`` traces from the remainder, covering every present stratum.

    Each present stratum contributes at least one case (coverage), then the leftover
    budget is filled by a stratum-blind sample of what is left — all via the injected
    rng so the selection is deterministic for a seeded source.
    """
    by_stratum: dict[Stratum, list[TraceRecord]] = {}
    for t in remainder:
        by_stratum.setdefault(t.stratum, []).append(t)

    selected: list[TraceRecord] = []
    selected_ids: set[str] = set()
    # 1) one guaranteed pick per present stratum (deterministic order by stratum value).
    for stratum in sorted(by_stratum, key=lambda s: s.value):
        if len(selected) >= budget:
            break
        pool = by_stratum[stratum]
        pick = rng.sample(pool, 1)[0]
        assert isinstance(pick, TraceRecord)
        selected.append(pick)
        selected_ids.add(pick.trace_id)
    # 2) fill the rest from everything not yet chosen.
    leftover = [t for t in remainder if t.trace_id not in selected_ids]
    fill = max(0, budget - len(selected))
    if fill and leftover:
        k = min(fill, len(leftover))
        for picked in rng.sample(leftover, k):
            assert isinstance(picked, TraceRecord)
            selected.append(picked)
    return selected[:budget]


def _to_case(trace: TraceRecord) -> EvalCase:
    """Project a trace to a core EvalCase, riding metadata in the inputs mapping."""
    inputs: dict[str, object] = dict(trace.inputs)
    inputs[_STRATUM_KEY] = trace.stratum.value
    inputs[_REFERENCE_KEY] = trace.incumbent_output
    inputs[_OUTCOME_LABEL_KEY] = trace.outcome_label
    return EvalCase(
        id=f"case-{trace.trace_id}",
        inputs=inputs,
        label_source=trace.label_source,
        source_trace_id=trace.trace_id,
    )


def stratum_of(case: EvalCase) -> Stratum:
    """Read back the stratum a case was drawn from."""
    return Stratum(case.inputs[_STRATUM_KEY])


def reference_output_of(case: EvalCase) -> str:
    """Read back the incumbent model's reference output stored on a case."""
    value = case.inputs[_REFERENCE_KEY]
    assert isinstance(value, str)
    return value


def validate_judge(
    *,
    labels: Sequence[HumanLabel],
    judge_scores: Mapping[str, float],
    threshold: float,
) -> JudgeValidationResult:
    """Validate an LLM judge against human labels; validated iff TPR/TNR>=0.9 and n>=50.

    A missing judge score is treated as a negative judgement (a conservative
    fail) so an unscored case can never silently inflate agreement. ``validated``
    is the AND of the three gates: no judge is trusted on fewer than 50 labels or
    below 0.9 on either rate (§8.2).

    Args:
        labels: the committed human-labeled cases (the N>=50 fixture).
        judge_scores: judge score per ``case_id``; ``>= threshold`` is a judge "pass".
        threshold: the judge-pass cutoff in the open interval ``(0, 1)``.

    Raises:
        ValueError: if ``threshold`` is not within ``(0, 1)``.
    """
    if not 0.0 < threshold < 1.0:
        raise ValueError(f"threshold must be in (0, 1); got {threshold}")
    n = len(labels)
    tp = fn = tn = fp = 0
    for label in labels:
        judge_pass = judge_scores.get(label.case_id, 0.0) >= threshold
        if label.human_positive:
            if judge_pass:
                tp += 1
            else:
                fn += 1
        elif judge_pass:
            fp += 1
        else:
            tn += 1
    tpr = tp / (tp + fn) if (tp + fn) else 0.0
    tnr = tn / (tn + fp) if (tn + fp) else 0.0
    validated = n >= 50 and tpr >= 0.9 and tnr >= 0.9
    return JudgeValidationResult(tpr=tpr, tnr=tnr, n=n, validated=validated)


def load_committed_human_labels() -> tuple[HumanLabel, ...]:
    """Load the committed N>=50 human-label fixture shipped with the package (§8.2).

    The fixture is the non-negotiable human ground-truth subset every judge is
    validated against; it travels with the package so validation is reproducible.
    """
    raw = (
        resources.files("valuemaxx.eval.fixtures")
        .joinpath(_HUMAN_LABELS_FILE)
        .read_text(encoding="utf-8")
    )
    # json.loads is typed Any; narrow it to a concrete object shape at this boundary.
    parsed: object = json.loads(raw)
    if not isinstance(parsed, list):
        raise TypeError("human-label fixture must be a JSON array")
    rows = cast("list[object]", parsed)
    labels: list[HumanLabel] = []
    for row in rows:
        if not isinstance(row, dict):
            raise TypeError("each human-label row must be a JSON object")
        row_map = cast("dict[str, object]", row)
        labels.append(
            HumanLabel(
                case_id=str(row_map["case_id"]),
                prediction=str(row_map["prediction"]),
                reference=str(row_map["reference"]),
                human_positive=bool(row_map["human_positive"]),
            )
        )
    return tuple(labels)


__all__ = [
    "JudgeValidationResult",
    "TraceRecord",
    "build_dataset",
    "load_committed_human_labels",
    "reference_output_of",
    "stratum_of",
    "validate_judge",
]
