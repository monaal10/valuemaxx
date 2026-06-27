"""Tests for SUGGEST — drafting an unconfirmed attribution rule from natural language (H10)."""

from __future__ import annotations

from valuemaxx.core import SignalClass
from valuemaxx.onboarding.capabilities import ScanResult, ScanSite
from valuemaxx.onboarding.suggest import suggest_attribution_rule

from tests.stubs import StubSignalMapper


def _scan_with(*sites: ScanSite) -> ScanResult:
    return ScanResult(
        run_boundaries=(), outcome_sites=sites, entity_ids=(), warnings=()
    )


def _site(symbol: str, kind: str = "status_setter") -> ScanSite:
    return ScanSite.model_validate(
        {
            "kind": kind,
            "file": "app.py",
            "line": 1,
            "symbol": symbol,
            "snippet": f"def {symbol}(): ...",
        }
    )


def test_suggest_returns_unconfirmed_candidate() -> None:
    scan = _scan_with(_site("mark_resolved"))
    sug = suggest_attribution_rule(
        "when a ticket is resolved",
        source="def mark_resolved(t): t.status='resolved'",
        scan=scan,
        signal_mapper=StubSignalMapper(),
    )
    assert sug.confirmed is False
    assert sug.rule.confirmed is False


def test_suggest_maps_nl_to_a_concrete_site() -> None:
    scan = _scan_with(_site("mark_resolved"), _site("charge_customer", kind="external_write"))
    sug = suggest_attribution_rule(
        "resolved tickets",
        source="",
        scan=scan,
        signal_mapper=StubSignalMapper(),
    )
    assert "mark_resolved" in sug.rule.match_target
    assert sug.confidence > 0.5


def test_suggest_signal_is_system_mapped() -> None:
    scan = _scan_with(_site("mark_resolved"))
    sug = suggest_attribution_rule(
        "ticket resolved", source="", scan=scan, signal_mapper=StubSignalMapper()
    )
    # status setter -> system maps to confirmed (never taken from the NL text)
    assert sug.rule.signal == SignalClass.OUTCOME_CONFIRMED


def test_suggest_low_confidence_when_no_matching_site() -> None:
    scan = _scan_with(_site("charge_customer", kind="external_write"))
    sug = suggest_attribution_rule(
        "when the moon is full",
        source="",
        scan=scan,
        signal_mapper=StubSignalMapper(),
    )
    assert sug.confidence < 0.5


def test_suggest_redacts_secret_in_source_and_nl() -> None:
    scan = _scan_with(_site("mark_resolved"))
    leak = "api_key = 'sk-ant-api03-SUGGESTLEAK0123456789abcdefghij'"
    sug = suggest_attribution_rule(
        f"resolved {leak}",
        source=f"def mark_resolved(): {leak}",
        scan=scan,
        signal_mapper=StubSignalMapper(),
    )
    blob = sug.model_dump_json()
    assert "sk-ant-api03-SUGGESTLEAK0123456789abcdefghij" not in blob
