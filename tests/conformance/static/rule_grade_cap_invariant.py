"""grade_cap_invariant — reliable only off outcome_label/human_labeled (green; owner EVAL).

A ``RELIABLE`` eval grade is constructible ONLY off an ``outcome_label`` or
``human_labeled`` rung; a judge/reference rung is capped at ``directional`` (§8.2).
This is enforced two ways, both checked here:

  * **structurally in core** — :class:`~valuemaxx.core.EvalRecommendation`'s
    ``_grade_cap_invariant`` model_validator raises if ``grade=RELIABLE`` is paired
    with a judge/reference label source;
  * **in the eval grader** — :func:`valuemaxx.eval.grade_for_label_source` maps
    judge/reference to ``directional``, so the eval funnel never *produces* a
    capped-violating grade.

``flags_violation`` inspects a source string for the violation marker (a RELIABLE
grade paired with a judge/reference source). The negative fixture is the synthetic
violation; the foundation subject is the real eval grader source, which caps
honestly. ``core_rejects_reliable_off_judge`` exercises the runtime invariant.
"""

from __future__ import annotations

from tests.conformance.astutil import package_src
from tests.conformance.rulebase import Rule, RuleKind

_MARKERS: tuple[str, ...] = ("grade=RELIABLE, label_source=LLM_JUDGE", "label_source=REFERENCE")


def _flags(subject: object) -> bool:
    assert isinstance(subject, str)
    return any(marker in subject for marker in _MARKERS)


def _negative_fixture() -> object:
    return "EvalRecommendation(grade=RELIABLE, label_source=LLM_JUDGE)\n"


def _foundation_subject() -> object:
    # the real eval grader: judge/reference rungs are capped at directional.
    return (package_src("eval") / "grade.py").read_text()


def core_rejects_reliable_off_judge() -> bool:
    """The core model_validator raises when RELIABLE is paired with a judge rung.

    Returns True iff every judge/reference label source raises on a RELIABLE grade
    and every outcome/human source is accepted — the grade cap, executed.
    """
    from decimal import Decimal
    from uuid import UUID

    from valuemaxx.core import EvalGrade, EvalRecommendation, LabelSource, TenantId

    tenant = TenantId(UUID("00000000-0000-0000-0000-000000000001"))

    def _make(label_source: LabelSource) -> None:
        EvalRecommendation(
            tenant_id=tenant,
            recommended_model="cheap",
            incumbent_model="big",
            grade=EvalGrade.RELIABLE,
            label_source=label_source,
            parity_ci95=(Decimal("0.1"), Decimal("0.9")),
            latency_p50_ms=1.0,
            latency_p95_ms=2.0,
            latency_p99_ms=3.0,
            sample_disagreements=(),
            gap_distribution={},
            pareto_frontier=(),
            methodology="x",
        )

    for capped in (LabelSource.LLM_JUDGE, LabelSource.REFERENCE):
        try:
            _make(capped)
        except ValueError:
            continue
        return False  # a judge/reference RELIABLE was wrongly accepted
    for ok in (LabelSource.OUTCOME_LABEL, LabelSource.HUMAN_LABELED):
        _make(ok)  # must NOT raise
    return True


RULE = Rule(
    name="grade_cap_invariant",
    kind=RuleKind.STATIC,
    green_now=True,
    owner_task="EVAL",
    flags_violation=_flags,
    negative_fixture=_negative_fixture,
    foundation_subject=_foundation_subject,
)
