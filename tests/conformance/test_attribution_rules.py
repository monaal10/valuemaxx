"""Substantive checks for the three ATTRIBUTION-owned conformance rules (§6.3, §3.1).

These exercise the *live* invariants behind the three rules the attribution package
owns, beyond the negative-fixture/foundation-subject checks in ``test_meta.py``:

- ``resolver_emits_only_its_own_tier`` — the framework rejects a foreign tier.
- ``candidate_likely_never_billing_grade`` — advisory results are never billing-grade.
- ``no_user_override_of_confidence_mapping`` — the scoring map has no user setter.
"""

from __future__ import annotations

import pytest

from tests.conformance.static import (
    rule_candidate_likely_never_billing_grade,
    rule_no_user_override_of_confidence_mapping,
    rule_resolver_emits_only_its_own_tier,
)


@pytest.mark.conformance
def test_resolver_emits_only_its_own_tier_is_enforced() -> None:
    """A resolver emitting a foreign tier is rejected by the validated entrypoint."""
    assert rule_resolver_emits_only_its_own_tier.foundation_foreign_tier_is_rejected() is True


@pytest.mark.conformance
def test_candidate_likely_never_billing_grade_holds() -> None:
    """No advisory (candidate/likely) AttributionResult reports as billing-grade."""
    rule = rule_candidate_likely_never_billing_grade
    offenders = rule.foundation_advisory_results_are_not_billing_grade()
    assert offenders == [], f"advisory tiers wrongly billing-grade: {offenders}"


@pytest.mark.conformance
def test_no_user_override_of_confidence_mapping_holds() -> None:
    """The scoring module exposes no setter and its tier->label table is read-only."""
    offenders = rule_no_user_override_of_confidence_mapping.foundation_scoring_exposes_no_setter()
    assert offenders == [], f"confidence-mapping override surface present: {offenders}"
