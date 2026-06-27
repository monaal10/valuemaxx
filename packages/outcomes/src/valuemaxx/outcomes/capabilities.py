"""OUT-E: the outcomes package's capability registration (§3, H6 — push registration).

:func:`register` adds this package's three capabilities to the shared registry so every
surface (API/MCP/CLI) projects them from one source:

* ``ingest_webhook_outcome`` — ``webhook_inbound``, **API only** (an inbound webhook is
  not a CLI command). The real verify-before-parse pipeline is
  :func:`~valuemaxx.outcomes.webhook.receive_webhook`; the capability declares the
  contract the API surface wires that pipeline to.
* ``validate_outcome_rule`` — ``request_response`` on API|MCP|CLI. Parses an
  ``outcomes.yaml`` document through the safe loader + AST allowlist and reports whether
  it is valid (the onboarding agent's ``validate_*`` tool). An ``eval`` predicate is
  rejected here (``no_eval_in_predicate``).
* ``list_outcome_rules`` — ``request_response`` on API|MCP|CLI. Returns one summary per
  declared rule (name, match kind, declared signal).

The request/response envelopes are pydantic models that live in this allowlisted
``capabilities.py`` (capability I/O contracts, not domain types — see the
``no_type_outside_core`` rule). The domain types they reference still live only in
``valuemaxx.core``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel
from valuemaxx.capabilities import Mode, Surface, capability
from valuemaxx.outcomes.errors import OutcomeRuleError
from valuemaxx.outcomes.loader import load_rules
from valuemaxx.outcomes.predicate import SafePredicateValidator

if TYPE_CHECKING:
    from valuemaxx.capabilities import Registry

_REQUEST_RESPONSE_SURFACES = Surface.API | Surface.MCP | Surface.CLI


class IngestWebhookOutcomeRequest(BaseModel):
    """The raw inbound webhook envelope (verified + parsed by the runtime pipeline)."""

    source: str
    body: bytes
    signature: str
    ingest_key: str


class IngestWebhookOutcomeResponse(BaseModel):
    """The acknowledgement: whether the webhook verified and how its run_id was bound."""

    verified: bool
    accepted: bool
    extracted_via: str | None


class ValidateOutcomeRuleRequest(BaseModel):
    """An ``outcomes.yaml`` document to validate."""

    yaml_text: str


class ValidateOutcomeRuleResponse(BaseModel):
    """Whether the document is valid, the rule count, and the first error if invalid."""

    ok: bool
    rule_count: int
    error: str | None


class OutcomeRuleSummary(BaseModel):
    """A one-line summary of a declared rule (no executable predicate echoed)."""

    name: str
    match_kind: str
    signal: str


class ListOutcomeRulesRequest(BaseModel):
    """An ``outcomes.yaml`` document to summarize."""

    yaml_text: str


class ListOutcomeRulesResponse(BaseModel):
    """The per-rule summaries, plus a parse error string when the document is invalid."""

    rules: list[OutcomeRuleSummary]
    error: str | None


def ingest_webhook_outcome_handler(
    request: IngestWebhookOutcomeRequest,
) -> IngestWebhookOutcomeResponse:
    """Capability descriptor handler for inbound webhook ingest.

    The real verify-before-parse + bind pipeline is :func:`receive_webhook`, which the
    API surface wires with the per-source security material and emitter. This handler
    documents the contract shape; it never verifies with an absent secret.
    """
    return IngestWebhookOutcomeResponse(verified=False, accepted=False, extracted_via=None)


def validate_outcome_rule_handler(
    request: ValidateOutcomeRuleRequest,
) -> ValidateOutcomeRuleResponse:
    """Validate an outcomes.yaml document through the safe loader (rejects eval/dunder)."""
    try:
        rules = load_rules(request.yaml_text, validator=SafePredicateValidator())
    except OutcomeRuleError as exc:
        return ValidateOutcomeRuleResponse(ok=False, rule_count=0, error=str(exc))
    return ValidateOutcomeRuleResponse(ok=True, rule_count=len(rules), error=None)


def list_outcome_rules_handler(request: ListOutcomeRulesRequest) -> ListOutcomeRulesResponse:
    """Summarize each declared rule; report a parse error instead of raising."""
    try:
        rules = load_rules(request.yaml_text, validator=SafePredicateValidator())
    except OutcomeRuleError as exc:
        return ListOutcomeRulesResponse(rules=[], error=str(exc))
    summaries = [
        OutcomeRuleSummary(name=r.name, match_kind=r.match.match_kind, signal=r.signal)
        for r in rules
    ]
    return ListOutcomeRulesResponse(rules=summaries, error=None)


def register(registry: Registry) -> None:
    """Register the outcomes package's three capabilities into ``registry``."""
    registry.register(
        capability(
            name="ingest_webhook_outcome",
            input_model=IngestWebhookOutcomeRequest,
            output_model=IngestWebhookOutcomeResponse,
            handler=ingest_webhook_outcome_handler,
            description=(
                "Ingest an inbound outcome webhook: verify signature + ingest key before "
                "parse, then bind run_id via T3 echo or fall back to T4 entity (labeled)."
            ),
            surfaces=Surface.API,
            mode=Mode.WEBHOOK_INBOUND,
        )
    )
    registry.register(
        capability(
            name="validate_outcome_rule",
            input_model=ValidateOutcomeRuleRequest,
            output_model=ValidateOutcomeRuleResponse,
            handler=validate_outcome_rule_handler,
            description=(
                "Validate an outcomes.yaml document through the safe loader and AST "
                "allowlist; an eval/exec/dunder predicate is rejected, never executed."
            ),
            surfaces=_REQUEST_RESPONSE_SURFACES,
            mode=Mode.REQUEST_RESPONSE,
        )
    )
    registry.register(
        capability(
            name="list_outcome_rules",
            input_model=ListOutcomeRulesRequest,
            output_model=ListOutcomeRulesResponse,
            handler=list_outcome_rules_handler,
            description="Summarize the rules declared in an outcomes.yaml document.",
            surfaces=_REQUEST_RESPONSE_SURFACES,
            mode=Mode.REQUEST_RESPONSE,
        )
    )


__all__ = [
    "IngestWebhookOutcomeRequest",
    "IngestWebhookOutcomeResponse",
    "ListOutcomeRulesRequest",
    "ListOutcomeRulesResponse",
    "OutcomeRuleSummary",
    "ValidateOutcomeRuleRequest",
    "ValidateOutcomeRuleResponse",
    "ingest_webhook_outcome_handler",
    "list_outcome_rules_handler",
    "register",
    "validate_outcome_rule_handler",
]
