"""Tests for PROPOSE — building unconfirmed candidate outcome rules from a scan."""

from __future__ import annotations

import _onboarding_helpers
from valuemaxx.core import BindingTier, SignalClass
from valuemaxx.onboarding.capabilities import ScanResult, ScanSite
from valuemaxx.onboarding.propose import build_proposal


def _site(**kw: object) -> ScanSite:
    base: dict[str, object] = {
        "kind": "status_setter",
        "file": "app.py",
        "line": 1,
        "symbol": "mark_resolved",
        "snippet": "ticket.status = 'resolved'",
    }
    base.update(kw)
    return ScanSite.model_validate(base)


def test_status_setter_proposes_exact_confirmed_rule() -> None:
    scan = ScanResult(
        run_boundaries=(),
        outcome_sites=(_site(kind="status_setter", symbol="mark_resolved"),),
        entity_ids=(),
        warnings=(),
    )
    proposal = build_proposal(scan, signal_mapper=_onboarding_helpers.StubSignalMapper())
    assert len(proposal.rules) == 1
    rule = proposal.rules[0]
    assert rule.tier in (BindingTier.EXACT, BindingTier.DETERMINISTIC)
    assert rule.signal == SignalClass.OUTCOME_CONFIRMED
    assert rule.confirmed is False  # never confirmed at proposal time


def test_echoing_external_write_gets_t3_injection_deterministic() -> None:
    scan = ScanResult(
        run_boundaries=(),
        outcome_sites=(
            _site(
                kind="external_write",
                symbol="charge_customer",
                system="stripe",
                echoes_metadata=True,
            ),
        ),
        entity_ids=(),
        warnings=(),
    )
    proposal = build_proposal(scan, signal_mapper=_onboarding_helpers.StubSignalMapper())
    rule = proposal.rules[0]
    assert rule.tier == BindingTier.DETERMINISTIC
    assert rule.run_id_injection is not None
    assert rule.run_id_injection.system == "stripe"


def test_non_echoing_external_write_is_candidate_with_warning_and_no_injection() -> None:
    scan = ScanResult(
        run_boundaries=(),
        outcome_sites=(
            _site(
                kind="external_write",
                symbol="push_to_salesforce",
                system="salesforce",
                echoes_metadata=False,
            ),
        ),
        entity_ids=(),
        warnings=(),
    )
    proposal = build_proposal(scan, signal_mapper=_onboarding_helpers.StubSignalMapper())
    rule = proposal.rules[0]
    assert rule.tier == BindingTier.CANDIDATE
    assert rule.run_id_injection is None
    assert any("salesforce" in w for w in rule.warnings)


def test_external_write_function_site_cannot_become_confirmed() -> None:
    scan = ScanResult(
        run_boundaries=(),
        outcome_sites=(
            _site(
                kind="external_write",
                symbol="charge_customer",
                system="stripe",
                echoes_metadata=True,
            ),
        ),
        entity_ids=(),
        warnings=(),
    )
    proposal = build_proposal(scan, signal_mapper=_onboarding_helpers.StubSignalMapper())
    # external-write attempts are action_attempted, never confirmed (system-owned)
    assert proposal.rules[0].signal == SignalClass.ACTION_ATTEMPTED


def test_proposal_carries_entity_ids() -> None:
    scan = ScanResult(
        run_boundaries=(),
        outcome_sites=(_site(),),
        entity_ids=("ticket_id", "customer_id"),
        warnings=(),
    )
    proposal = build_proposal(scan, signal_mapper=_onboarding_helpers.StubSignalMapper())
    assert proposal.entity_ids == ("ticket_id", "customer_id")


def test_shared_costs_absent_when_no_tier23_inputs() -> None:
    scan = ScanResult(run_boundaries=(), outcome_sites=(_site(),), entity_ids=(), warnings=())
    proposal = build_proposal(scan, signal_mapper=_onboarding_helpers.StubSignalMapper())
    assert proposal.shared_costs_present is False


def test_proposal_contains_no_secret() -> None:
    leak = "ticket.status = 'x'  # key=sk-ant-api03-LEAKEDvalue0123456789abcdefgh"
    scan = ScanResult(
        run_boundaries=(),
        outcome_sites=(_site(snippet=leak),),
        entity_ids=(),
        warnings=(),
    )
    proposal = build_proposal(scan, signal_mapper=_onboarding_helpers.StubSignalMapper())
    assert "sk-ant-api03-LEAKEDvalue0123456789abcdefgh" not in proposal.model_dump_json()


def test_webhook_handler_proposes_confirmed_rule() -> None:
    scan = ScanResult(
        run_boundaries=(),
        outcome_sites=(_site(kind="webhook_handler", symbol="handle_webhook"),),
        entity_ids=(),
        warnings=(),
    )
    proposal = build_proposal(scan, signal_mapper=_onboarding_helpers.StubSignalMapper())
    rule = proposal.rules[0]
    assert rule.match_kind == "webhook"
    assert rule.signal == SignalClass.OUTCOME_CONFIRMED
