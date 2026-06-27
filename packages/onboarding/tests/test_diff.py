"""Tests for DIFF — the hunks-only, secret-free reviewable diff (H12)."""

from __future__ import annotations

import pytest
from valuemaxx.core import BindingTier, SignalClass
from valuemaxx.onboarding.capabilities import (
    OutcomeRuleCandidate,
    Proposal,
    ScanResult,
    ScanSite,
)
from valuemaxx.onboarding.diff import build_reviewable_diff
from valuemaxx.onboarding.errors import SecretEncounteredError


def _proposal() -> Proposal:
    rule = OutcomeRuleCandidate(
        name="ticket_resolved",
        match_kind="status_setter",
        match_target="app.py:mark_resolved",
        when="args.status == 'resolved'",
        signal=SignalClass.OUTCOME_CONFIRMED,
        tier=BindingTier.EXACT,
    )
    return Proposal(rules=(rule,), entity_ids=("ticket_id",), warnings=())


def _scan_with_boundary() -> ScanResult:
    boundary = ScanSite(
        kind="run_boundary",
        file="app.py",
        line=5,
        symbol="run_agent",
        snippet="def run_agent(): ...",
    )
    return ScanResult(
        run_boundaries=(boundary,), outcome_sites=(), entity_ids=("ticket_id",), warnings=()
    )


def test_diff_is_hunks_only_not_whole_files() -> None:
    diff = build_reviewable_diff(_proposal(), _scan_with_boundary())
    # every hunk is a bounded slice (has a header + a small line count), not a whole file
    assert diff.hunks
    for hunk in diff.hunks:
        assert hunk.header.startswith("@@")
        assert len(hunk.lines) <= 20


def test_diff_adds_outcomes_yaml() -> None:
    diff = build_reviewable_diff(_proposal(), _scan_with_boundary())
    yaml_hunks = [h for h in diff.hunks if h.file == "outcomes.yaml"]
    assert yaml_hunks
    assert any("ticket_resolved" in line for h in yaml_hunks for line in h.lines)


def test_diff_inserts_init_at_run_boundary() -> None:
    diff = build_reviewable_diff(_proposal(), _scan_with_boundary())
    app_hunks = [h for h in diff.hunks if h.file == "app.py"]
    assert app_hunks
    body = "\n".join(line for h in app_hunks for line in h.lines)
    assert "valuemaxx" in body
    assert "init" in body


def test_diff_excludes_unmodified_files() -> None:
    # a scan with no run boundary -> no app.py hunk, only the config hunk
    scan = ScanResult(run_boundaries=(), outcome_sites=(), entity_ids=(), warnings=())
    diff = build_reviewable_diff(_proposal(), scan)
    assert all(h.file != "app.py" for h in diff.hunks)
    assert any(h.file == "outcomes.yaml" for h in diff.hunks)


def test_diff_never_contains_secret() -> None:
    leaky = OutcomeRuleCandidate(
        name="leaky",
        match_kind="status_setter",
        match_target="app.py:mark",
        when="args.status == 'ok'",
        signal=SignalClass.OUTCOME_CONFIRMED,
        tier=BindingTier.EXACT,
    )
    proposal = Proposal(rules=(leaky,), entity_ids=(), warnings=())
    diff = build_reviewable_diff(proposal, _scan_with_boundary())
    blob = diff.model_dump_json()
    assert "sk-ant-" not in blob


def test_diff_raises_if_a_hunk_would_carry_a_secret() -> None:
    # a run boundary whose snippet smuggles a secret that bypassed redaction must be
    # caught by the final assert_no_secret gate (defence in depth).
    bad_boundary = ScanSite.model_construct(
        kind="run_boundary",
        file="app.py",
        line=1,
        symbol="sk-ant-api03-BYPASS0123456789abcdefghijklmno",
        snippet="x",
        system=None,
        echoes_metadata=False,
        entity_ids=(),
    )
    scan = ScanResult(
        run_boundaries=(bad_boundary,), outcome_sites=(), entity_ids=(), warnings=()
    )
    with pytest.raises(SecretEncounteredError):
        build_reviewable_diff(_proposal(), scan, redact_first=False)
