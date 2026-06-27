"""Webhook result + the C3 Protocols (§6).

:class:`WebhookResult` records the outcome of an inbound webhook: ``verified`` is
set only after signature + ingest-key verification *before* the payload is parsed
(§3.2). ``extracted_via`` records how the run id was recovered — ``echo`` (T3
round-trip) or ``entity_fallback`` (T4), or None when unbound.

:class:`OutcomesPredicateValidator` and :class:`SignalClassMapper` are the C3
Protocols whose real implementations land in the G2 ``outcomes`` package; declared
here so they live in the typed spine and downstream code depends on the interface.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal, Protocol, runtime_checkable

from valuemaxx.core.base import StrictModel
from valuemaxx.core.ids import RunId


class WebhookResult(StrictModel):
    """The verified, parsed result of an inbound outcome webhook."""

    verified: bool
    source: str
    event_type: str
    run_id: RunId | None
    extracted_via: Literal["echo", "entity_fallback"] | None
    payload: Mapping[str, object]


@runtime_checkable
class OutcomesPredicateValidator(Protocol):
    """Validates an outcome predicate expression against an AST allowlist (§6.1).

    The implementation rejects ``eval``/``exec``/dunder access; only a safe subset
    of comparisons/attribute reads is permitted (the ``no_eval_in_predicate`` rule).
    """

    def validate(self, expr: str) -> None:
        """Validate ``expr``; raise if it uses a disallowed construct."""
        ...


@runtime_checkable
class SignalClassMapper(Protocol):
    """Maps a match to its system-owned signal class (§6.4).

    A function/HTTP match can never yield ``outcome_confirmed`` unless the result
    is authoritative; the signal class is system-owned and never user-set (the
    ``signal_class_never_user_set`` rule).
    """

    def map_signal(self, *, match_kind: str, declared: str) -> str:
        """Return the system-assigned signal class for a match."""
        ...


__all__ = ["OutcomesPredicateValidator", "SignalClassMapper", "WebhookResult"]
