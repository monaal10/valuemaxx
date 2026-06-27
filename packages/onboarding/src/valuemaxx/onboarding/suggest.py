"""SUGGEST — draft an UNCONFIRMED attribution rule from natural language (H10).

:func:`suggest_attribution_rule` takes a natural-language description ("when a ticket
is resolved") and the surrounding source, redacts both, finds the best-matching
scanned site by token overlap, and drafts an
:class:`~valuemaxx.onboarding.capabilities.SuggestedRule`. The result is **always**
``confirmed=False`` — the agent drafts, it never guesses-and-applies (design §7 /
H10). Confidence reflects how directly the language matched a concrete site; when
nothing matches, confidence is low and the caller is expected to ask for human input.

The signal class on the drafted rule is the system-mapped value, never lifted from
the free-text request — an attempt described as "confirmed" in prose does not become
a confirmed outcome.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from valuemaxx.core import BindingTier, SignalClass
from valuemaxx.onboarding.capabilities import OutcomeRuleCandidate, ScanResult, SuggestedRule
from valuemaxx.onboarding.propose import build_proposal
from valuemaxx.onboarding.redact import redact

if TYPE_CHECKING:
    from valuemaxx.core import SignalClassMapper
    from valuemaxx.onboarding.capabilities import ScanSite

_WORD = re.compile(r"[a-z0-9]+")
# Confidence when the best site shares no tokens with the request.
_FLOOR_CONFIDENCE = 0.1
# Confidence ceiling for a strong (multi-token) match.
_MAX_CONFIDENCE = 0.95


def _tokens(text: str) -> set[str]:
    """Lowercased word/identifier tokens of ``text`` (symbols split on underscores)."""
    out: set[str] = set()
    for raw in _WORD.findall(text.lower()):
        out.add(raw)
        out.update(part for part in raw.split("_") if part)
    return out


def _score_site(request_tokens: set[str], site: ScanSite) -> float:
    """Overlap score in [0, 1] between the request and a site's symbol tokens."""
    site_tokens = _tokens(site.symbol)
    if not site_tokens:
        return 0.0
    overlap = request_tokens & site_tokens
    return len(overlap) / len(site_tokens)


def _confidence(score: float) -> float:
    """Map a raw overlap score to a confidence in [floor, max]."""
    if score <= 0.0:
        return _FLOOR_CONFIDENCE
    return min(_MAX_CONFIDENCE, _FLOOR_CONFIDENCE + score * (_MAX_CONFIDENCE - _FLOOR_CONFIDENCE))


def suggest_attribution_rule(
    natural_language: str,
    *,
    source: str,
    scan: ScanResult,
    signal_mapper: SignalClassMapper,
) -> SuggestedRule:
    """Draft an UNCONFIRMED :class:`SuggestedRule` mapping ``natural_language`` to a site.

    Both ``natural_language`` and ``source`` are redacted before use. The best site is
    chosen by token overlap; its candidate rule is built via the same system-owned
    :func:`~valuemaxx.onboarding.propose.build_proposal` path (so the signal class and
    tier are system-mapped). Confidence is low when nothing matches — never a silent
    high-confidence guess.
    """
    clean_nl = redact(natural_language)
    _ = redact(source)  # redacted defensively; not echoed into the suggestion
    request_tokens = _tokens(clean_nl)

    if not scan.outcome_sites:
        # Nothing to bind to: draft the weakest possible (likely) unmatched rule with a
        # system-mapped signal — never a guess, always confirmed=False, low confidence.
        unmatched_signal = SignalClass(
            signal_mapper.map_signal(match_kind="status_setter", declared="")
        )
        empty_rule = OutcomeRuleCandidate(
            name="unmatched",
            match_kind="status_setter",
            match_target="",
            when="True",
            signal=unmatched_signal,
            tier=BindingTier.LIKELY,
        )
        return SuggestedRule(
            natural_language=clean_nl, rule=empty_rule, confidence=_FLOOR_CONFIDENCE
        )

    scored = [(_score_site(request_tokens, site), site) for site in scan.outcome_sites]
    best_score, best_site = max(scored, key=lambda pair: pair[0])

    # Reuse the system-owned proposal path so the rule's signal/tier are mapped, not guessed.
    single = ScanResult(
        run_boundaries=(),
        outcome_sites=(best_site,),
        entity_ids=scan.entity_ids,
        warnings=(),
    )
    rule = build_proposal(single, signal_mapper=signal_mapper).rules[0]
    return SuggestedRule(
        natural_language=clean_nl, rule=rule, confidence=_confidence(best_score)
    )


__all__ = ["suggest_attribution_rule"]
