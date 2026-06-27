"""Generate ``llms.txt`` from the capability registry (the agent-integration surface).

Agents read installed source and integration files; ``llms.txt`` is the single,
generated index of everything the product exposes. It lists EVERY capability (name,
surfaces, mode, description) and an ``instructions`` section that corrects the priors
an LLM agent is likely to bring: the honesty axes are system-owned (binding tier is
system-owned, signal_class is system-mapped — never user-set), and an attribution
rule should be drafted via ``suggest_attribution_rule`` (which returns an unconfirmed
candidate a human confirms) rather than guessed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from valuemaxx.capabilities import Surface

if TYPE_CHECKING:
    from valuemaxx.capabilities import AnyCapability, Registry

_INSTRUCTIONS = """\
## instructions (read before calling any capability)

valuemaxx measures cost-per-outcome WITH CONFIDENCE. The three honesty axes are
system-owned and MUST NOT be set or guessed by an agent or user:

- Binding tier (exact | deterministic | candidate | likely) is SYSTEM-OWNED. Never
  present an inferred match as exact. candidate/likely are advisory and never
  billing-grade.
- signal_class (action_attempted | outcome_confirmed | outcome_retracted) is
  SYSTEM-MAPPED from the outcome source. A successful tool call is action_attempted
  unless the result is authoritative; never write signal_class yourself.
- Cost provenance (measured | estimated | allocated | provider_reconciled |
  manual_reconciled) is system-owned; an estimate is never rendered as billed.

Every rollup carries minimum_tier + confidence_distribution — never collapse them
into a bare number.

To wire an attribution rule, call `suggest_attribution_rule`: it returns an
UNCONFIRMED candidate for a human to confirm. Do not hand-write or auto-apply a rule.
To check an outcomes.yaml, call `validate_outcome_rule`. To preview a draft, call
`scaffold_outcome_rule` (also returns an unconfirmed draft).
"""


def _surface_names(cap: AnyCapability) -> str:
    return "|".join(
        surface.name for surface in Surface if surface in cap.surfaces and surface.name is not None
    )


def _capability_line(cap: AnyCapability) -> str:
    return (
        f"- {cap.name} [surfaces={_surface_names(cap)}; mode={cap.mode.value}]: {cap.description}"
    )


def generate_llms_txt(registry: Registry) -> str:
    """Generate the ``llms.txt`` index for ``registry`` (lists every capability).

    Deterministic: capabilities are listed in registration order. The output has a
    title, a capabilities list (one line per capability with its surfaces + mode),
    and the system-owned-axes instructions section.
    """
    lines = [
        "# valuemaxx — AI margin intelligence (cost-per-outcome with confidence)",
        "",
        "## capabilities",
        "",
    ]
    lines.extend(_capability_line(cap) for cap in registry.all())
    lines.extend(["", _INSTRUCTIONS])
    return "\n".join(lines)


__all__ = ["generate_llms_txt"]
