"""Tests for DRYRUN — cost-per-outcome preview via an injected rollup reader (C3)."""

from __future__ import annotations

from decimal import Decimal

import _helpers
from valuemaxx.core import BindingTier
from valuemaxx.onboarding.capabilities import CostPerOutcome
from valuemaxx.onboarding.dryrun import dry_run


def test_dry_run_returns_preview_with_both_h7_fields() -> None:
    reader = _helpers.StubRollupReader(
        CostPerOutcome(
            cost_usd=Decimal("1.50"),
            minimum_tier=BindingTier.CANDIDATE,
            confidence_distribution={BindingTier.CANDIDATE: 2, BindingTier.EXACT: 1},
        )
    )
    preview = dry_run("ticket_resolved", rollup_reader=reader)
    assert preview.cost_per_outcome_usd == Decimal("1.50")
    assert preview.minimum_tier == BindingTier.CANDIDATE
    assert preview.confidence_distribution == {
        BindingTier.CANDIDATE: 2,
        BindingTier.EXACT: 1,
    }


def test_dry_run_returns_none_cost_when_no_outcomes() -> None:
    reader = _helpers.StubRollupReader(None)
    preview = dry_run("never_bound", rollup_reader=reader)
    assert preview.cost_per_outcome_usd is None
    # H7 fields still present (conservative: a likely-only, empty distribution)
    assert preview.minimum_tier == BindingTier.LIKELY


def test_dry_run_preserves_outcome_name() -> None:
    reader = _helpers.StubRollupReader(None)
    preview = dry_run("my_outcome", rollup_reader=reader)
    assert preview.outcome_name == "my_outcome"
