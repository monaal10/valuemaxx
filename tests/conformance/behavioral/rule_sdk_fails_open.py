"""sdk_fails_open — an injected throwing client must not break the host (RED; owner CAPTURE).

Runtime rule: with a throwing instrumentation client injected, the host call still
returns and our exception is suppressed + counted (never propagated into user code).
``flags_violation`` inspects a host-call outcome record and flags it iff our internal
exception escaped into the host call path.

Authored RED-but-meaningful: the negative fixture is an outcome where the internal
exception propagated. The foundation assertion is skip-marked until CAPTURE provides
the real fail-open wrapper.
"""

from __future__ import annotations

from typing import cast

from tests.conformance.rulebase import Rule, RuleKind


def _flags(subject: object) -> bool:
    """subject is a dict: {'host_returned': bool, 'internal_exc_propagated': bool}."""
    assert isinstance(subject, dict)
    record = cast("dict[str, object]", subject)
    return bool(record.get("internal_exc_propagated")) or not record.get("host_returned")


def _negative_fixture() -> object:
    # the SDK let its internal exception escape into the host call -> violation
    return {"host_returned": False, "internal_exc_propagated": True}


RULE = Rule(
    name="sdk_fails_open",
    kind=RuleKind.BEHAVIORAL,
    green_now=False,
    owner_task="CAPTURE",
    flags_violation=_flags,
    negative_fixture=_negative_fixture,
    foundation_subject=None,
)
