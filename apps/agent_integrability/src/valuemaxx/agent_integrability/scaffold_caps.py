"""Agent-facing scaffold/validate capabilities — drafts are always UNCONFIRMED (H10).

These are the ``scaffold_*`` / ``validate_*`` tools an agent uses while wiring
valuemaxx. They are projected onto MCP (among other surfaces) like any capability.
Critically, anything that *proposes* a rule returns a DRAFT explicitly marked
unconfirmed (binding_tier ``candidate``): the system never auto-applies a scaffolded
rule, and an agent must hand it to a human to confirm. This mirrors onboarding's
``suggest_attribution_rule`` discipline and upholds the honesty axes — a draft can
never present an inferred binding as exact.

The onboarding package already owns ``suggest_attribution_rule`` and
``validate_outcome_rule``; this module adds the distinct helper tools
``scaffold_outcome_rule`` (draft an outcomes.yaml rule) and ``validate_init`` (check
an SDK init snippet).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel
from valuemaxx.capabilities import Mode, Surface, capability

if TYPE_CHECKING:
    from valuemaxx.capabilities import Registry

_SURFACES = Surface.API | Surface.MCP | Surface.CLI


class ScaffoldOutcomeRuleInput(BaseModel):
    """A natural-language description of the outcome to scaffold a rule for."""

    outcome_name: str
    description: str
    signal_hint: str


class ScaffoldOutcomeRuleOutput(BaseModel):
    """A DRAFT outcomes.yaml rule — always unconfirmed (a human confirms)."""

    draft_yaml: str
    confirmed: bool
    binding_tier: str
    note: str


class ValidateInitInput(BaseModel):
    """An SDK init snippet to validate (does it call ``valuemaxx.init()``?)."""

    snippet: str


class ValidateInitOutput(BaseModel):
    """Whether the init snippet is valid, with a reason when it is not."""

    valid: bool
    reason: str | None


def scaffold_outcome_rule(request: ScaffoldOutcomeRuleInput) -> ScaffoldOutcomeRuleOutput:
    """Draft an outcomes.yaml rule from a description — UNCONFIRMED candidate (H10).

    The draft is never authoritative: ``confirmed`` is False and ``binding_tier`` is
    ``candidate``. signal_class is left for the system to map; the hint is recorded
    as a comment, not asserted as truth.
    """
    draft_yaml = (
        "outcomes:\n"
        f"  - name: {request.outcome_name}\n"
        f"    # description: {request.description}\n"
        f"    # signal_hint (NOT authoritative; system maps signal_class): "
        f"{request.signal_hint}\n"
        "    match:\n"
        "      kind: entity_key  # confirm the durable id this binds on\n"
    )
    return ScaffoldOutcomeRuleOutput(
        draft_yaml=draft_yaml,
        confirmed=False,
        binding_tier="candidate",
        note=(
            "UNCONFIRMED draft. Review and confirm before applying; valuemaxx never "
            "auto-applies a scaffolded rule, and signal_class/binding tier are "
            "system-owned."
        ),
    )


def validate_init(request: ValidateInitInput) -> ValidateInitOutput:
    """Validate that an init snippet calls ``valuemaxx.init()``."""
    if "valuemaxx.init(" in request.snippet:
        return ValidateInitOutput(valid=True, reason=None)
    return ValidateInitOutput(
        valid=False,
        reason="snippet does not call valuemaxx.init(); add it at the app entrypoint",
    )


def register_scaffold_caps(registry: Registry) -> None:
    """Register the scaffold/validate helper capabilities (surfaces include MCP)."""
    registry.register(
        capability(
            name="scaffold_outcome_rule",
            input_model=ScaffoldOutcomeRuleInput,
            output_model=ScaffoldOutcomeRuleOutput,
            handler=scaffold_outcome_rule,
            description=(
                "Draft an outcomes.yaml rule from a description. Returns an "
                "UNCONFIRMED candidate (binding tier candidate) a human confirms; "
                "never auto-applied."
            ),
            surfaces=_SURFACES,
            mode=Mode.REQUEST_RESPONSE,
        )
    )
    registry.register(
        capability(
            name="validate_init",
            input_model=ValidateInitInput,
            output_model=ValidateInitOutput,
            handler=validate_init,
            description="Validate that an SDK init snippet calls valuemaxx.init().",
            surfaces=_SURFACES,
            mode=Mode.REQUEST_RESPONSE,
        )
    )


__all__ = [
    "ScaffoldOutcomeRuleInput",
    "ScaffoldOutcomeRuleOutput",
    "ValidateInitInput",
    "ValidateInitOutput",
    "register_scaffold_caps",
    "scaffold_outcome_rule",
    "validate_init",
]
