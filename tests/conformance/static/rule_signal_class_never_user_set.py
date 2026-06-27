"""signal_class_never_user_set — the signal class is system-owned (GREEN; owner OUTCOMES).

The outcome signal class is decided exclusively by the system
:class:`~valuemaxx.outcomes.signal.SystemSignalClassMapper`: a function/HTTP match can
never yield ``outcome_confirmed`` and no user path assigns ``signal_class`` directly.
``flags_violation`` scans a source string for a direct ``signal_class`` write or a
``set_signal_class`` setter. The negative fixture is a synthetic user override; the
foundation subject is the real mapper source, which exposes no setter and never assigns
``signal_class`` — it only *returns* the system-chosen class string.
"""

from __future__ import annotations

from tests.conformance.astutil import package_src
from tests.conformance.rulebase import Rule, RuleKind

_MARKERS: tuple[str, ...] = ("signal_class =", "signal_class=", "set_signal_class")


def _flags(subject: object) -> bool:
    assert isinstance(subject, str)
    return any(marker in subject for marker in _MARKERS)


def _negative_fixture() -> object:
    return "outcome.signal_class = OUTCOME_CONFIRMED  # user override\n"


def _foundation_subject() -> object:
    # The system-owned mapper: returns the signal class, exposes no setter, never assigns it.
    return (package_src("outcomes") / "signal.py").read_text()


RULE = Rule(
    name="signal_class_never_user_set",
    kind=RuleKind.STATIC,
    green_now=True,
    owner_task="OUTCOMES",
    flags_violation=_flags,
    negative_fixture=_negative_fixture,
    foundation_subject=_foundation_subject,
)
