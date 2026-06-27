"""Tests for the onboarding capability-I/O / config-envelope models.

These pydantic models live in ``capabilities.py`` (the config-AST allowlist of the
``no_type_outside_core`` rule): they shape this package's capability requests/
responses and the outcomes.yaml config envelope — they are NOT domain types (those
stay in ``valuemaxx.core``).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from valuemaxx.core import BindingTier, SignalClass

from valuemaxx.onboarding.capabilities import (
    DryRunPreview,
    OutcomeRuleCandidate,
    RunIdInjection,
    ScanResult,
    ScanSite,
    SuggestedRule,
)


def test_scan_site_round_trips() -> None:
    site = ScanSite(
        kind="status_setter",
        file="app/tickets.py",
        line=12,
        symbol="mark_resolved",
        snippet="ticket.status = 'resolved'",
    )
    assert site.kind == "status_setter"
    assert ScanSite.model_validate(site.model_dump()) == site


def test_scan_site_is_frozen() -> None:
    site = ScanSite(kind="run_boundary", file="m.py", line=1, symbol="run", snippet="agent()")
    with pytest.raises(ValidationError):
        site.line = 2  # type: ignore[misc]


def test_scan_result_holds_sites_entities_warnings() -> None:
    result = ScanResult(
        run_boundaries=(),
        outcome_sites=(),
        entity_ids=("ticket_id", "customer_id"),
        warnings=(),
    )
    assert result.entity_ids == ("ticket_id", "customer_id")


def test_outcome_rule_candidate_is_unconfirmed_by_default() -> None:
    rule = OutcomeRuleCandidate(
        name="ticket_resolved",
        match_kind="status_setter",
        match_target="app.tickets.mark_resolved",
        when="args.status == 'resolved'",
        signal=SignalClass.OUTCOME_CONFIRMED,
        tier=BindingTier.DETERMINISTIC,
        run_id_injection=None,
        warnings=(),
    )
    assert rule.confirmed is False


def test_run_id_injection_round_trips() -> None:
    inj = RunIdInjection(
        system="stripe",
        target_field="metadata.atm_run_id",
        write_site="app.billing.charge",
    )
    assert RunIdInjection.model_validate(inj.model_dump()) == inj


def test_suggested_rule_is_unconfirmed() -> None:
    sug = SuggestedRule(
        natural_language="when a ticket is closed",
        rule=OutcomeRuleCandidate(
            name="ticket_closed",
            match_kind="status_setter",
            match_target="app.tickets.close",
            when="args.status == 'closed'",
            signal=SignalClass.OUTCOME_CONFIRMED,
            tier=BindingTier.DETERMINISTIC,
            run_id_injection=None,
            warnings=(),
        ),
        confidence=0.9,
    )
    assert sug.confirmed is False
    assert sug.rule.confirmed is False


def test_dry_run_preview_carries_both_h7_fields() -> None:
    preview = DryRunPreview(
        outcome_name="ticket_resolved",
        cost_per_outcome_usd=None,
        minimum_tier=BindingTier.CANDIDATE,
        confidence_distribution={BindingTier.CANDIDATE: 3, BindingTier.EXACT: 1},
    )
    # both H7 fields present and serialized
    dumped = preview.model_dump()
    assert "minimum_tier" in dumped
    assert "confidence_distribution" in dumped
