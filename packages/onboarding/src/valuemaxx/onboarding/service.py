"""SERVICE + REGISTER — the OnboardingService and its 5 capabilities (design §7).

:class:`OnboardingService` wires the stages (scan → propose → suggest → validate →
render → diff → dry-run) behind injected seams: the
:class:`~valuemaxx.core.SignalClassMapper` and
:class:`~valuemaxx.core.OutcomesPredicateValidator` Protocols, an injected
:class:`~valuemaxx.onboarding.dryrun.MetricsRollupReader`, and an optional read-only
:class:`~valuemaxx.onboarding.github_app.ReadOnlyGithubApp`. The service imports no
concrete store/surface/sibling logic package — only the Protocols.

:func:`register` projects the five capabilities into a registry (push registration,
H6): ``scan_codebase``, ``suggest_attribution_rule`` (H10), ``validate_outcome_rule``,
``dry_run_outcomes`` (async_job — a preview is a background job), and
``propose_onboarding_diff`` (request_response, on API|MCP|CLI). Every response is
secret-free by construction (each stage redacts and the diff stage asserts).

The capability request/response envelopes are defined in ``capabilities.py`` (the
config-AST allowlist) and re-exported here for callers.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from valuemaxx.capabilities import Mode, Surface, capability
from valuemaxx.onboarding.capabilities import (
    DryRunPreview,
    DryRunRequest,
    ProposeRequest,
    ProposeResponse,
    ScanRequest,
    ScanResult,
    SuggestRequest,
    SuggestResponse,
    ValidateRequest,
    ValidateResponse,
)
from valuemaxx.onboarding.diff import build_reviewable_diff
from valuemaxx.onboarding.dryrun import dry_run
from valuemaxx.onboarding.propose import build_proposal
from valuemaxx.onboarding.render import render_outcomes_yaml
from valuemaxx.onboarding.scan import scan_codebase
from valuemaxx.onboarding.suggest import suggest_attribution_rule
from valuemaxx.onboarding.validate import validate_rule

if TYPE_CHECKING:
    from valuemaxx.capabilities import Registry
    from valuemaxx.core import OutcomesPredicateValidator, SignalClassMapper
    from valuemaxx.onboarding.dryrun import MetricsRollupReader
    from valuemaxx.onboarding.github_app import ReadOnlyGithubApp

__all__ = [
    "DryRunRequest",
    "OnboardingService",
    "ProposeRequest",
    "ProposeResponse",
    "ScanRequest",
    "SuggestRequest",
    "SuggestResponse",
    "ValidateRequest",
    "ValidateResponse",
    "register",
]


class OnboardingService:
    """Wires the onboarding stages behind injected Protocol seams.

    No concrete store/surface/sibling logic package is imported — the mapper,
    validator, rollup reader, and (optional) read-only GitHub App are all injected.
    """

    def __init__(
        self,
        *,
        signal_mapper: SignalClassMapper,
        predicate_validator: OutcomesPredicateValidator,
        rollup_reader: MetricsRollupReader,
        github_app: ReadOnlyGithubApp | None = None,
    ) -> None:
        self._signal_mapper = signal_mapper
        self._predicate_validator = predicate_validator
        self._rollup_reader = rollup_reader
        self._github_app = github_app

    def scan(self, request: ScanRequest) -> ScanResult:
        """Scan the codebase at ``request.root`` (read-only, secret-redacted)."""
        return scan_codebase(Path(request.root))

    def propose(self, request: ProposeRequest) -> ProposeResponse:
        """Build the proposal + reviewable diff + rendered outcomes.yaml from a scan."""
        proposal = build_proposal(
            request.scan,
            signal_mapper=self._signal_mapper,
            shared_costs_inputs=request.shared_costs_inputs,
        )
        diff = build_reviewable_diff(proposal, request.scan)
        outcomes_yaml = render_outcomes_yaml(proposal)
        return ProposeResponse(proposal=proposal, diff=diff, outcomes_yaml=outcomes_yaml)

    def suggest(self, request: SuggestRequest) -> SuggestResponse:
        """Draft an UNCONFIRMED rule from natural language (H10)."""
        suggestion = suggest_attribution_rule(
            request.natural_language,
            source=request.source,
            scan=request.scan,
            signal_mapper=self._signal_mapper,
        )
        return SuggestResponse(suggestion=suggestion)

    def validate(self, request: ValidateRequest) -> ValidateResponse:
        """Validate a candidate rule against the predicate + signal Protocols.

        Raises :class:`~valuemaxx.onboarding.errors.UnsafePredicateError` on a bad
        predicate or a tampered (non-system-mapped) signal; otherwise returns valid.
        """
        validate_rule(
            request.rule,
            predicate_validator=self._predicate_validator,
            signal_mapper=self._signal_mapper,
        )
        return ValidateResponse(valid=True)

    def dry_run(self, request: DryRunRequest) -> DryRunPreview:
        """Preview cost-per-outcome via the injected rollup reader (carries both H7 fields)."""
        return dry_run(request.outcome_name, rollup_reader=self._rollup_reader)


def register(registry: Registry) -> None:
    """Register the five onboarding capabilities (push registration, H6).

    The handlers are unbound capability contracts (typed I/O + surfaces + mode); a
    surface binds them to a configured :class:`OnboardingService` at projection time.
    These handlers raise if invoked unbound — the registry stores the contract, not a
    runnable closure (the concrete mapper/validator/reader are injected at G4/G5).
    """

    def _unbound(name: str) -> str:
        return (
            f"capability {name!r} must be bound to a configured OnboardingService "
            "by the surface before invocation"
        )

    def _scan(_: ScanRequest) -> ScanResult:
        raise NotImplementedError(_unbound("scan_codebase"))

    def _suggest(_: SuggestRequest) -> SuggestResponse:
        raise NotImplementedError(_unbound("suggest_attribution_rule"))

    def _validate(_: ValidateRequest) -> ValidateResponse:
        raise NotImplementedError(_unbound("validate_outcome_rule"))

    def _dry_run(_: DryRunRequest) -> DryRunPreview:
        raise NotImplementedError(_unbound("dry_run_outcomes"))

    def _propose(_: ProposeRequest) -> ProposeResponse:
        raise NotImplementedError(_unbound("propose_onboarding_diff"))

    all_surfaces = Surface.API | Surface.MCP | Surface.CLI | Surface.NOTIFY
    rr_surfaces = Surface.API | Surface.MCP | Surface.CLI

    registry.register(
        capability(
            name="scan_codebase",
            input_model=ScanRequest,
            output_model=ScanResult,
            handler=_scan,
            description="Read-only AST scan of a codebase for run boundaries and outcome sites.",
            surfaces=rr_surfaces,
            mode=Mode.REQUEST_RESPONSE,
        )
    )
    registry.register(
        capability(
            name="suggest_attribution_rule",
            input_model=SuggestRequest,
            output_model=SuggestResponse,
            handler=_suggest,
            description="Draft an UNCONFIRMED attribution rule from a natural-language request.",
            surfaces=all_surfaces,
            mode=Mode.REQUEST_RESPONSE,
        )
    )
    registry.register(
        capability(
            name="validate_outcome_rule",
            input_model=ValidateRequest,
            output_model=ValidateResponse,
            handler=_validate,
            description="Validate a proposed outcome rule against the safe-predicate allowlist.",
            surfaces=rr_surfaces,
            mode=Mode.REQUEST_RESPONSE,
        )
    )
    registry.register(
        capability(
            name="dry_run_outcomes",
            input_model=DryRunRequest,
            output_model=DryRunPreview,
            handler=_dry_run,
            description="Preview cost-per-outcome for a proposed outcome (carries H7 confidence).",
            surfaces=all_surfaces,
            mode=Mode.ASYNC_JOB,
        )
    )
    registry.register(
        capability(
            name="propose_onboarding_diff",
            input_model=ProposeRequest,
            output_model=ProposeResponse,
            handler=_propose,
            description="Propose candidate outcome rules + a hunks-only reviewable diff.",
            surfaces=rr_surfaces,
            mode=Mode.REQUEST_RESPONSE,
        )
    )
