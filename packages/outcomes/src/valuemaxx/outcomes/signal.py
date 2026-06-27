"""OUT-B: the system-owned signal-class mapper (§6.4 honesty axis).

The outcome signal class (``action_attempted`` | ``outcome_confirmed`` |
``outcome_retracted``) is a system honesty axis — it is **never** user-settable. A
rule may *declare* a preference, but :class:`SystemSignalClassMapper` has the final
say (the ``signal_class_never_user_set`` conformance rule).

The load-bearing invariant: a **function** or **HTTP** match can never yield
``outcome_confirmed``. A successful tool call / HTTP 200 is not business success
(METR: ~half of test-passing PRs would not merge), so those non-authoritative kinds
are clamped to ``action_attempted`` regardless of what the rule declared. Only the
authoritative kinds — ``webhook`` (the vendor's own confirmation), ``orm_save``, and
``status_transition`` — may carry a declared ``outcome_confirmed`` through.

``outcome_retracted`` is never an emit-time declaration: retraction is a later flip
of an already-confirmed outcome (§6.4 H8, OUT-E), so declaring it on a rule is a
schema error caught here.
"""

from __future__ import annotations

from typing import Final

from valuemaxx.core import SignalClass

# Match kinds whose result is authoritative enough to carry a confirmed outcome.
# function/http are deliberately excluded: a 200 is an attempt, not a confirmation.
_AUTHORITATIVE_KINDS: Final[frozenset[str]] = frozenset(
    {"webhook", "orm_save", "status_transition"}
)
_NON_AUTHORITATIVE_KINDS: Final[frozenset[str]] = frozenset({"function", "http"})
_ALL_KINDS: Final[frozenset[str]] = _AUTHORITATIVE_KINDS | _NON_AUTHORITATIVE_KINDS


class SystemSignalClassMapper:
    """The :class:`~valuemaxx.core.SignalClassMapper` implementation (system-owned).

    ``map_signal`` takes the match kind and the rule's *declared* preference and
    returns the system-assigned signal class. It is the only place a signal class is
    decided; no caller writes ``signal_class`` directly.
    """

    def map_signal(self, *, match_kind: str, declared: str) -> str:
        """Return the system-assigned signal class for a match.

        Args:
            match_kind: one of function/http/webhook/orm_save/status_transition.
            declared: the rule's declared preference (action_attempted/outcome_confirmed).

        Raises:
            ValueError: on an unknown ``match_kind`` or ``declared`` value, or if a
                rule declares ``outcome_retracted`` (retraction is a later flip, not
                an emit-time signal).
        """
        if match_kind not in _ALL_KINDS:
            raise ValueError(
                f"unknown match_kind {match_kind!r}; expected one of {sorted(_ALL_KINDS)}"
            )
        declared_class = self._parse_declared(declared)

        # System override: non-authoritative kinds can never be confirmed.
        if declared_class is SignalClass.OUTCOME_CONFIRMED and match_kind in _AUTHORITATIVE_KINDS:
            return SignalClass.OUTCOME_CONFIRMED.value
        return SignalClass.ACTION_ATTEMPTED.value

    @staticmethod
    def _parse_declared(declared: str) -> SignalClass:
        try:
            declared_class = SignalClass(declared)
        except ValueError as exc:
            raise ValueError(
                f"unknown declared signal class {declared!r}; "
                f"expected action_attempted or outcome_confirmed"
            ) from exc
        if declared_class is SignalClass.OUTCOME_RETRACTED:
            raise ValueError(
                "a rule cannot declare outcome_retracted; retraction is a later flip (H8)"
            )
        return declared_class


__all__ = ["SystemSignalClassMapper"]
