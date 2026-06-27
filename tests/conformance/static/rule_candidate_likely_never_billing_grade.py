"""candidate_likely_never_billing_grade — advisory tiers are never billing-grade.

Owner ATTRIBUTION (now GREEN). ``candidate`` (T4 entity-match) and ``likely`` (T5
semantic) bindings are advisory and review-queued; they must never be fed to
billing-grade metrics (§3.1, §4). A code path that bills a candidate/likely binding
as graded is a violation.

``flags_violation`` flags source that bills a candidate/likely tier as billing-grade
(the negative fixture). The foundation subject is the real cascade source, which
upholds the invariant. ``foundation_advisory_results_are_not_billing_grade``
additionally exercises the live invariant on the core ``AttributionResult``.
"""

from __future__ import annotations

from tests.conformance.astutil import package_src
from tests.conformance.rulebase import Rule, RuleKind

_MARKERS: tuple[str, ...] = ("bill_as_grade", "billing_grade = True")


def _flags(subject: object) -> bool:
    assert isinstance(subject, str)
    return any(marker in subject for marker in _MARKERS)


def _negative_fixture() -> object:
    return "if tier in (CANDIDATE, LIKELY): bill_as_grade(metric)\n"


def _foundation_subject() -> object:
    # The real cascade source enqueues candidate/likely for review; it never bills.
    return (package_src("attribution") / "cascade.py").read_text()


def foundation_advisory_results_are_not_billing_grade() -> list[str]:
    """Exercise the live invariant: candidate/likely AttributionResults are advisory.

    Returns the names of any binding tier (candidate/likely) for which an
    ``AttributionResult`` wrongly reports ``is_billing_grade`` (should be empty).
    """
    from uuid import UUID

    from valuemaxx.core import AttributionResult, BindingTier, OutcomeEventId, RunId, TenantId

    offenders: list[str] = []
    for tier in (BindingTier.CANDIDATE, BindingTier.LIKELY):
        result = AttributionResult(
            tenant_id=TenantId(UUID(int=1)),
            outcome_id=OutcomeEventId("oc"),
            run_id=RunId("r"),
            tier=tier,
            bound_by="x",
            candidates=(),
            review_required=True,
        )
        if result.is_billing_grade:
            offenders.append(tier.value)
    return offenders


RULE = Rule(
    name="candidate_likely_never_billing_grade",
    kind=RuleKind.STATIC,
    green_now=True,
    owner_task="ATTRIBUTION",
    flags_violation=_flags,
    negative_fixture=_negative_fixture,
    foundation_subject=_foundation_subject,
)
