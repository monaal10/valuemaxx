"""PROPOSE — turn a scan into UNCONFIRMED candidate outcome rules (design §7 step 2).

For each discovered outcome site, :func:`build_proposal` drafts an
:class:`~valuemaxx.onboarding.capabilities.OutcomeRuleCandidate`:

* in-process sites (status setter / mark_* / ORM write) → ``exact`` binding (the
  rule fires synchronously at the call site);
* echoing external writes (Stripe/HubSpot/Zendesk) → a declarative ``run_id``
  injection block + ``deterministic`` binding (the later webhook echoes it back);
* non-echoing external writes (Salesforce …) → no injection, ``candidate`` binding,
  and a warning naming the system (T4 entity-fallback territory);
* webhook handlers → ``deterministic`` binding (the inbound payload carries the id).

The signal class is always the system-mapped value (``signal_mapper.map_signal``,
the :class:`~valuemaxx.core.SignalClassMapper` seam) — never user-set, so a function
attempt can never masquerade as a confirmed outcome. Every rule is ``confirmed=False``
(human review is the only path to confirmation), and every captured string is
re-redacted defensively before it enters a proposal field.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from valuemaxx.core import BindingTier, SignalClass
from valuemaxx.core.wire import INJECTED_RUN_ID_FIELD
from valuemaxx.onboarding.capabilities import (
    MatchKind,
    OutcomeRuleCandidate,
    Proposal,
    RunIdInjection,
    ScanSite,
)
from valuemaxx.onboarding.redact import redact

if TYPE_CHECKING:
    from valuemaxx.core import SignalClassMapper
    from valuemaxx.onboarding.capabilities import ScanResult

# Map a discovered site kind to the outcomes.yaml match kind.
_SITE_TO_MATCH: dict[str, MatchKind] = {
    "status_setter": "status_setter",
    "mark_function": "mark_function",
    "orm_write": "orm_write",
    "external_write": "external_write",
    "webhook_handler": "webhook",
}

# Site kinds that bind synchronously in-process (exact).
_IN_PROCESS_KINDS = frozenset({"status_setter", "mark_function", "orm_write"})

# The run-id metadata field injected into an echoing system's outbound object. Sourced
# from the cross-language wire contract so onboard's proposal and the runtime T3 injector
# (both SDKs) default to the identical path — they cannot drift.
_INJECTED_FIELD = INJECTED_RUN_ID_FIELD


def _signal_for(site: ScanSite, mapper: SignalClassMapper) -> SignalClass:
    """The system-owned signal class for a site (never user-set)."""
    match_kind = _SITE_TO_MATCH[site.kind]
    return SignalClass(mapper.map_signal(match_kind=match_kind, declared=""))


def _default_when(site: ScanSite) -> str:
    """A conservative default predicate for the site (redacted, human-editable)."""
    if site.kind == "status_setter":
        return "args.status != None"
    if site.kind == "webhook_handler":
        return "event.type != None"
    return "True"


def _rule_for_site(site: ScanSite, mapper: SignalClassMapper) -> OutcomeRuleCandidate:
    """Draft one unconfirmed candidate rule for a discovered site."""
    match_kind = _SITE_TO_MATCH[site.kind]
    signal = _signal_for(site, mapper)
    injection: RunIdInjection | None = None
    warnings: tuple[str, ...] = ()

    if site.kind in _IN_PROCESS_KINDS:
        tier = BindingTier.EXACT
    elif site.kind == "webhook_handler":
        tier = BindingTier.DETERMINISTIC
    elif site.kind == "external_write" and site.echoes_metadata:
        tier = BindingTier.DETERMINISTIC
        injection = RunIdInjection(
            system=redact(site.system or "unknown"),
            target_field=_INJECTED_FIELD,
            write_site=redact(site.symbol),
        )
    else:  # non-echoing external write
        tier = BindingTier.CANDIDATE
        system = redact(site.system or "unknown")
        warnings = (
            f"{system} does not echo injected metadata; deterministic T3 binding is "
            f"unavailable. Falling back to entity-id matching (candidate/T4); a human "
            f"must confirm before this is trusted.",
        )

    return OutcomeRuleCandidate(
        name=redact(site.symbol),
        match_kind=match_kind,
        match_target=redact(f"{site.file}:{site.symbol}"),
        when=redact(_default_when(site)),
        signal=signal,
        tier=tier,
        run_id_injection=injection,
        warnings=warnings,
    )


def build_proposal(
    scan: ScanResult,
    *,
    signal_mapper: SignalClassMapper,
    shared_costs_inputs: bool = False,
) -> Proposal:
    """Build a reviewable :class:`Proposal` of UNCONFIRMED candidate rules from a scan.

    ``shared_costs_inputs`` is True only when the operator has Tier-2/3 cost inputs
    (GPU seconds, monthly bills …); absent those, ``shared_costs_present`` stays
    False and no shared_costs.yaml is implied (M6 — never report a partial number as
    complete).
    """
    rules = tuple(_rule_for_site(site, signal_mapper) for site in scan.outcome_sites)
    warnings = tuple(redact(w) for w in scan.warnings)
    return Proposal(
        rules=rules,
        entity_ids=tuple(redact(e) for e in scan.entity_ids),
        shared_costs_present=shared_costs_inputs,
        warnings=warnings,
    )


__all__ = ["build_proposal"]
