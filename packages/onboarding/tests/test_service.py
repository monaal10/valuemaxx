"""Tests for SERVICE + register — the OnboardingService and its 5 capabilities."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import _onboarding_helpers
import pytest
from valuemaxx.capabilities import Mode, Registry, Surface
from valuemaxx.core import BindingTier, SignalClass
from valuemaxx.onboarding import register
from valuemaxx.onboarding.capabilities import CostPerOutcome
from valuemaxx.onboarding.service import (
    DryRunRequest,
    OnboardingService,
    ProposeRequest,
    ScanRequest,
    SuggestRequest,
    ValidateRequest,
)

if TYPE_CHECKING:
    from pathlib import Path

_APP = """
def run_agent(ticket_id):
    client = Anthropic()
    return client.complete(ticket_id)


def mark_resolved(ticket):
    ticket.status = "resolved"
"""


def _service(reader_result: CostPerOutcome | None = None) -> OnboardingService:
    return OnboardingService(
        signal_mapper=_onboarding_helpers.StubSignalMapper(),
        predicate_validator=_onboarding_helpers.StubPredicateValidator(),
        rollup_reader=_onboarding_helpers.StubRollupReader(reader_result),
    )


def _write_app(tmp_path: Path) -> Path:
    (tmp_path / "app.py").write_text(_APP)
    return tmp_path


# --- register() ---------------------------------------------------------------

_EXPECTED_CAPABILITIES = {
    "scan_codebase",
    "suggest_attribution_rule",
    "validate_outcome_rule",
    "dry_run_outcomes",
    "propose_onboarding_diff",
}


def test_register_adds_all_five_capabilities() -> None:
    registry = Registry()
    register(registry)
    names = {spec.name for spec in registry.all()}
    assert names >= _EXPECTED_CAPABILITIES


def test_register_is_callable_from_discovery() -> None:
    # discover_and_register requires a module-level callable register(registry)
    import valuemaxx.onboarding as pkg

    assert callable(pkg.register)


def test_suggest_capability_is_present_h10() -> None:
    registry = Registry()
    register(registry)
    assert any(s.name == "suggest_attribution_rule" for s in registry.all())


def test_dry_run_is_async_job_mode() -> None:
    registry = Registry()
    register(registry)
    dry = next(s for s in registry.all() if s.name == "dry_run_outcomes")
    assert dry.mode is Mode.ASYNC_JOB


def test_propose_is_request_response_on_api_mcp_cli() -> None:
    registry = Registry()
    register(registry)
    propose = next(s for s in registry.all() if s.name == "propose_onboarding_diff")
    assert propose.mode is Mode.REQUEST_RESPONSE
    for surface in (Surface.API, Surface.MCP, Surface.CLI):
        assert surface in propose.surfaces


# --- OnboardingService --------------------------------------------------------


def test_service_scan(tmp_path: Path) -> None:
    result = _service().scan(ScanRequest(root=str(_write_app(tmp_path))))
    assert any(s.symbol == "mark_resolved" for s in result.outcome_sites)


def test_service_propose_produces_unconfirmed_rules(tmp_path: Path) -> None:
    svc = _service()
    scan = svc.scan(ScanRequest(root=str(_write_app(tmp_path))))
    proposal = svc.propose(ProposeRequest(scan=scan))
    assert proposal.proposal.rules
    assert all(r.confirmed is False for r in proposal.proposal.rules)
    # the response carries a hunks-only diff
    assert proposal.diff.hunks


def test_service_suggest_returns_unconfirmed(tmp_path: Path) -> None:
    svc = _service()
    scan = svc.scan(ScanRequest(root=str(_write_app(tmp_path))))
    sug = svc.suggest(SuggestRequest(natural_language="ticket resolved", source="", scan=scan))
    assert sug.suggestion.confirmed is False


def test_service_validate_rejects_unsafe() -> None:
    from valuemaxx.onboarding.capabilities import OutcomeRuleCandidate
    from valuemaxx.onboarding.errors import UnsafePredicateError

    rule = OutcomeRuleCandidate(
        name="x",
        match_kind="status_setter",
        match_target="a.py:x",
        when="__import__('os')",
        signal=SignalClass.OUTCOME_CONFIRMED,
        tier=BindingTier.EXACT,
    )
    with pytest.raises(UnsafePredicateError):
        _service().validate(ValidateRequest(rule=rule))


def test_service_dry_run_carries_h7() -> None:
    reader_result = CostPerOutcome(
        cost_usd=Decimal("2.00"),
        minimum_tier=BindingTier.CANDIDATE,
        confidence_distribution={BindingTier.CANDIDATE: 1, BindingTier.EXACT: 1},
    )
    preview = _service(reader_result).dry_run(DryRunRequest(outcome_name="ticket_resolved"))
    assert preview.minimum_tier == BindingTier.CANDIDATE
    assert preview.confidence_distribution
    assert preview.cost_per_outcome_usd == Decimal("2.00")


def test_service_propose_response_never_contains_secret(tmp_path: Path) -> None:
    leak = "sk-ant-api03-SERVICELEAK0123456789abcdefghij"
    (tmp_path / "leaky.py").write_text(f'def mark_done(t):\n    t.status = "done"  # key={leak}\n')
    svc = _service()
    scan = svc.scan(ScanRequest(root=str(tmp_path)))
    proposal = svc.propose(ProposeRequest(scan=scan))
    assert leak not in proposal.model_dump_json()
