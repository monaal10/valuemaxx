"""Capability-I/O and config-envelope models for the onboarding agent.

These pydantic models are **not** domain types — domain types live only in
``valuemaxx.core`` (the ``no_type_outside_core`` rule). They shape this package's
capability requests/responses, the scan result, the proposed outcome rules, and
the outcomes.yaml config envelope. The file basename ``capabilities.py`` is on the
rule's config-AST allowlist for exactly this purpose.

The honesty axes ride through on ``valuemaxx.core`` enums (``SignalClass``,
``BindingTier``): a proposed rule's ``signal`` is always the system-mapped value
and a rule candidate is ``confirmed=False`` until a human reviews it.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Literal

from pydantic import Field
from valuemaxx.core import BindingTier, SignalClass
from valuemaxx.core.base import StrictModel

# System-owned scan-site taxonomy. A site is one of these kinds; the kind drives
# how the rule is proposed (in-process vs external write vs webhook).
SiteKind = Literal[
    "run_boundary",
    "status_setter",
    "mark_function",
    "orm_write",
    "external_write",
    "webhook_handler",
]

# How a proposed rule binds to code (mirrors the match shapes of outcomes.yaml).
MatchKind = Literal["status_setter", "mark_function", "orm_write", "external_write", "webhook"]


class ScanSite(StrictModel):
    """One discovered site in the scanned codebase (already secret-redacted).

    ``snippet`` has passed :func:`~valuemaxx.onboarding.redact.redact`, so it never
    carries a secret. ``echoes_metadata`` is True only for external-write sites whose
    target system echoes injected metadata back (Stripe/HubSpot/Zendesk).
    """

    kind: SiteKind
    file: str
    line: int
    symbol: str
    snippet: str
    system: str | None = None
    echoes_metadata: bool = False
    entity_ids: tuple[str, ...] = ()


class ScanResult(StrictModel):
    """The result of scanning a codebase: where to bind, what to bind, what's in scope."""

    run_boundaries: tuple[ScanSite, ...]
    outcome_sites: tuple[ScanSite, ...]
    entity_ids: tuple[str, ...]
    warnings: tuple[str, ...]


class RunIdInjection(StrictModel):
    """A declarative run_id-injection block (§6.1) for an echoing external system."""

    system: str
    target_field: str
    write_site: str


class OutcomeRuleCandidate(StrictModel):
    """A proposed outcome rule — UNCONFIRMED until a human reviews it.

    ``signal`` is the system-mapped signal class (never user-set); ``tier`` is the
    binding tier the wiring achieves (exact/deterministic/candidate/likely).
    ``confirmed`` is always False at proposal time.
    """

    name: str
    match_kind: MatchKind
    match_target: str
    when: str
    signal: SignalClass
    tier: BindingTier
    run_id_injection: RunIdInjection | None = None
    warnings: tuple[str, ...] = ()
    confirmed: Literal[False] = False


class Proposal(StrictModel):
    """The reviewable proposal: candidate rules + entity ids + warnings."""

    rules: tuple[OutcomeRuleCandidate, ...]
    entity_ids: tuple[str, ...]
    shared_costs_present: bool = False
    warnings: tuple[str, ...] = ()


class SuggestedRule(StrictModel):
    """A drafted rule from natural language — UNCONFIRMED (H10: never applied blindly)."""

    natural_language: str
    rule: OutcomeRuleCandidate
    confidence: float = Field(ge=0.0, le=1.0)
    confirmed: Literal[False] = False


class DiffHunk(StrictModel):
    """One hunk of a reviewable diff — a bounded slice of a file, never a whole file."""

    file: str
    header: str
    lines: tuple[str, ...]


class ReviewableDiff(StrictModel):
    """A hunks-only diff (H12): bounded changes, no whole-file contents, no secrets."""

    hunks: tuple[DiffHunk, ...]


class PullRequest(StrictModel):
    """The result of opening a PR: a branch + a body carrying ONLY the diff (H12).

    The body never contains raw repo file contents — the GitHub-App model emits the
    diff, not the codebase, so there is no off-box raw-source path.
    """

    branch: str
    title: str
    body: str


class CostPerOutcome(StrictModel):
    """The injected rollup reader's result for one outcome (carries both H7 fields).

    This is the wire shape the ``MetricsRollupReader`` seam returns — not a domain
    type (the domain rollup lives in ``valuemaxx.core``). ``cost_usd`` is None when
    no outcomes are bound yet.
    """

    cost_usd: Decimal | None
    minimum_tier: BindingTier
    confidence_distribution: Mapping[BindingTier, int]


class DryRunPreview(StrictModel):
    """A cost-per-outcome preview carrying BOTH H7 confidence fields (§3.1).

    ``cost_per_outcome_usd`` is None when there are no bound outcomes yet (no
    fabricated number). Both ``minimum_tier`` and ``confidence_distribution`` are
    always present so a surface can never collapse the confidence.
    """

    outcome_name: str
    cost_per_outcome_usd: Decimal | None
    minimum_tier: BindingTier
    confidence_distribution: Mapping[BindingTier, int]


# --- capability request/response envelopes ------------------------------------
# One typed request + response per registered capability (the surfaces project
# these). They are config/IO envelopes, not domain types.


class ScanRequest(StrictModel):
    """Request for ``scan_codebase``: the filesystem root to scan."""

    root: str


class ProposeRequest(StrictModel):
    """Request for ``propose_onboarding_diff``: a prior scan result."""

    scan: ScanResult
    shared_costs_inputs: bool = False


class ProposeResponse(StrictModel):
    """Response for ``propose_onboarding_diff``: the proposal + its reviewable diff."""

    proposal: Proposal
    diff: ReviewableDiff
    outcomes_yaml: str


class SuggestRequest(StrictModel):
    """Request for ``suggest_attribution_rule`` (H10): NL + source + a scan to match."""

    natural_language: str
    source: str
    scan: ScanResult


class SuggestResponse(StrictModel):
    """Response for ``suggest_attribution_rule``: an UNCONFIRMED suggested rule."""

    suggestion: SuggestedRule


class ValidateRequest(StrictModel):
    """Request for ``validate_outcome_rule``: the candidate rule to validate."""

    rule: OutcomeRuleCandidate


class ValidateResponse(StrictModel):
    """Response for ``validate_outcome_rule``: whether the rule passed validation."""

    valid: bool


class DryRunRequest(StrictModel):
    """Request for ``dry_run_outcomes``: the outcome to preview."""

    outcome_name: str


__all__ = [
    "CostPerOutcome",
    "DiffHunk",
    "DryRunPreview",
    "DryRunRequest",
    "MatchKind",
    "OutcomeRuleCandidate",
    "Proposal",
    "ProposeRequest",
    "ProposeResponse",
    "PullRequest",
    "ReviewableDiff",
    "RunIdInjection",
    "ScanRequest",
    "ScanResult",
    "ScanSite",
    "SiteKind",
    "SuggestRequest",
    "SuggestResponse",
    "SuggestedRule",
    "ValidateRequest",
    "ValidateResponse",
]
