"""RENDER — deterministic YAML/markdown rendering of a proposal (design §7).

Renders a reviewed :class:`~valuemaxx.onboarding.capabilities.Proposal` to the config
artifacts the SDK reads:

* :func:`render_outcomes_yaml` — the ``outcomes.yaml`` body. Deterministic: rules are
  stable-sorted by name and keys are emitted in a fixed order, with **no timestamps**,
  so the same proposal always renders byte-identical (a clean diff). Round-trips
  through :func:`yaml.safe_load`.
* :func:`render_shared_costs_yaml` — the ``shared_costs.yaml`` body, or ``None`` when
  the proposal has no Tier-2/3 inputs (M6 — an omitted file, never a fabricated zero).
* :func:`render_agents_md_snippet` — a short ``AGENTS.md`` note pointing the user's
  coding agent at the generated config.

Every rendered string is passed through :func:`~valuemaxx.onboarding.redact.redact`
so no secret can reach the YAML, even if one slipped through an upstream field.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import yaml
from valuemaxx.onboarding.redact import redact

if TYPE_CHECKING:
    from valuemaxx.onboarding.capabilities import OutcomeRuleCandidate, Proposal


def _rule_mapping(rule: OutcomeRuleCandidate) -> dict[str, object]:
    """The ordered, redacted mapping for one outcome rule (deterministic key order)."""
    mapping: dict[str, object] = {
        "name": redact(rule.name),
        "match_kind": rule.match_kind,
        "match_target": redact(rule.match_target),
        "when": redact(rule.when),
        "signal": rule.signal.value,
        "tier": rule.tier.value,
    }
    if rule.run_id_injection is not None:
        inj = rule.run_id_injection
        mapping["run_id_injection"] = {
            "system": redact(inj.system),
            "target_field": redact(inj.target_field),
            "write_site": redact(inj.write_site),
        }
    if rule.warnings:
        mapping["warnings"] = [redact(w) for w in rule.warnings]
    return mapping


def _dump(payload: object) -> str:
    """Deterministic YAML dump: sorted keys, block style, no timestamps, redacted."""
    text = yaml.safe_dump(payload, sort_keys=True, default_flow_style=False, allow_unicode=True)
    return redact(text)


def render_outcomes_yaml(proposal: Proposal) -> str:
    """Render the ``outcomes.yaml`` body for ``proposal`` (deterministic, secret-free).

    Rules are stable-sorted by name so re-rendering an unchanged proposal yields a
    byte-identical document (a clean review diff). Round-trips via ``yaml.safe_load``.
    """
    rules = sorted(proposal.rules, key=lambda r: r.name)
    payload: dict[str, object] = {
        "version": 1,
        "outcomes": [_rule_mapping(rule) for rule in rules],
        "entity_ids": sorted(redact(e) for e in proposal.entity_ids),
    }
    return _dump(payload)


def render_shared_costs_yaml(proposal: Proposal) -> str | None:
    """Render ``shared_costs.yaml``, or ``None`` when the proposal has no Tier-2/3 inputs.

    Absent inputs means no file (M6): we publish Tier-1 measured only and never emit a
    placeholder that could read as a complete allocation.
    """
    if not proposal.shared_costs_present:
        return None
    payload: dict[str, object] = {
        "version": 1,
        "shared_costs": [],
        "note": "operator-supplied Tier-2/3 inputs (GPU seconds, monthly bills) go here",
    }
    return _dump(payload)


def render_agents_md_snippet(proposal: Proposal) -> str:
    """Render a short AGENTS.md note pointing the user's coding agent at the config."""
    names = ", ".join(sorted(redact(r.name) for r in proposal.rules)) or "(none)"
    return (
        "## valuemaxx outcomes\n\n"
        "This repo declares cost-per-outcome rules in `outcomes.yaml` (read by the "
        "valuemaxx SDK at `init()`). Proposed outcomes: "
        f"{names}.\n\n"
        "These rules are UNCONFIRMED until a human reviews the generated diff.\n"
    )


__all__ = [
    "render_agents_md_snippet",
    "render_outcomes_yaml",
    "render_shared_costs_yaml",
]
