"""OUT-A: the ``outcomes.yaml`` rule schema (frozen dataclasses).

These are *config* objects, not domain models — they describe how to instrument an
app, not a captured event. They are deliberately frozen :mod:`dataclasses`, never
pydantic models: the ``no_type_outside_core`` conformance rule reserves pydantic
domain models for ``valuemaxx.core`` (the only place :class:`OutcomeEvent` lives).

A :class:`MatchSpec` declares **exactly one** of five match kinds — ``function`` |
``http`` | ``orm_save`` | ``status_transition`` | ``webhook`` — exposed uniformly via
:attr:`MatchSpec.match_kind` and :attr:`MatchSpec.target`. The ``when`` predicate is a
string that is **never** ``eval``'d (validated by the AST allowlist at load time).
:class:`RunIdInjectionSpec` is the T3 round-trip block (§6.1). :class:`OutcomeRule`
ties them together with ``value``/``bind``/``signal`` (a declared preference; the
:class:`~valuemaxx.outcomes.signal.SystemSignalClassMapper` has the final say).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from valuemaxx.outcomes.errors import OutcomeRuleSchemaError

# The five match kinds, in the order they are probed when exactly-one is enforced.
_MATCH_KINDS: Final[tuple[str, ...]] = (
    "function",
    "http",
    "orm_save",
    "status_transition",
    "webhook",
)


@dataclass(frozen=True, slots=True)
class MatchSpec:
    """Declares where an outcome is detected — exactly one of the five kinds.

    Exactly one of ``function``/``http``/``orm_save``/``status_transition``/``webhook``
    must be set; the others stay ``None``. ``when`` is the gating predicate (an
    AST-allowlisted string), and ``event`` is the webhook event type when relevant.
    """

    function: str | None = None
    http: str | None = None
    orm_save: str | None = None
    status_transition: str | None = None
    webhook: str | None = None
    when: str | None = None
    event: str | None = None

    def __post_init__(self) -> None:
        present = [k for k in _MATCH_KINDS if getattr(self, k) is not None]
        if len(present) != 1:
            raise OutcomeRuleSchemaError(
                f"a match must declare exactly one of {list(_MATCH_KINDS)}; got {present}"
            )

    @property
    def match_kind(self) -> str:
        """The single declared match kind (function/http/orm_save/status_transition/webhook)."""
        for kind in _MATCH_KINDS:
            if getattr(self, kind) is not None:
                return kind
        raise OutcomeRuleSchemaError("match has no kind")  # pragma: no cover — __post_init__ guards

    @property
    def target(self) -> str:
        """The symbol/route/source the match points at (the value of the declared kind)."""
        value = getattr(self, self.match_kind)
        assert isinstance(value, str)  # guaranteed by __post_init__
        return value


@dataclass(frozen=True, slots=True)
class RunIdInjectionSpec:
    """The T3 round-trip block (§6.1): stamp run_id outbound, recover it inbound.

    ``sdk_call`` is the outbound symbol we auto-wrap (e.g. ``stripe.PaymentIntent.create``);
    ``inject_into`` is the passthrough path we merge run_id into (e.g. ``metadata.run_id``);
    ``webhook_event`` is the echo event; ``extract_from`` is where run_id comes back.
    """

    sdk_call: str
    inject_into: str
    webhook_event: str
    extract_from: str


@dataclass(frozen=True, slots=True)
class OutcomeRule:
    """One declared outcome: a match, a value/bind, a declared signal, and optional T3 block."""

    name: str
    match: MatchSpec
    value: str | None = None
    bind: dict[str, str] = field(default_factory=lambda: {})
    signal: str = "action_attempted"
    run_id_injection: RunIdInjectionSpec | None = None


__all__ = ["MatchSpec", "OutcomeRule", "RunIdInjectionSpec"]
