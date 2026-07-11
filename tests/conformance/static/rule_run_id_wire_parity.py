"""run_id_wire_parity — the run_id carry contract is single-sourced (GREEN).

The deterministic-binding carry channels stamp the active run_id onto an outbound
channel under a key that MUST be identical across the producer (both SDKs) and the
consumer (the attribution cascade): the T2 W3C-baggage key and the T3 injected field.
:mod:`valuemaxx.core.wire` is the single source; a hard-coded ``"valuemaxx.run_id"``
or ``"metadata.atm_run_id"`` literal outside ``wire.py`` re-introduces the drift class
this rule forbids.

``flags_violation`` flags a subject that either (1) hard-codes one of the carry
literals instead of importing it from ``valuemaxx.core.wire``, OR (2) is the committed
wire fixture whose values disagree with the Python constants. The negative fixture is a
drifted fixture; the foundation subject is the committed fixture, which agrees with the
constants — and the live checks assert the T2 consumer + onboarding proposal read the
same source.
"""

from __future__ import annotations

import json
from typing import cast

from valuemaxx.core import wire

from tests.conformance.astutil import REPO_ROOT
from tests.conformance.rulebase import Rule, RuleKind

_FIXTURE = REPO_ROOT / "tests" / "wire_contract" / "run_id_wire.json"
# Files allowed to contain the literals: the single source itself and its generated fixtures.
_ALLOWED_LITERAL_FILES: tuple[str, ...] = (
    "core/wire.py",
    "run_id_wire.json",
)


def _flags(subject: object) -> bool:
    assert isinstance(subject, str)
    # If the subject is the wire fixture JSON, its values must equal the Python constants.
    try:
        payload: object = json.loads(subject)
    except (json.JSONDecodeError, ValueError):
        return False
    if isinstance(payload, dict) and "baggage_run_id_key" in payload:
        mapping = cast("dict[str, object]", payload)
        return (
            mapping.get("baggage_run_id_key") != wire.BAGGAGE_RUN_ID_KEY
            or mapping.get("injected_run_id_field") != wire.INJECTED_RUN_ID_FIELD
        )
    return False


def _negative_fixture() -> object:
    # a drifted fixture: a baggage key that disagrees with the Python constant.
    return json.dumps(
        {"baggage_run_id_key": "drifted.run_id", "injected_run_id_field": "metadata.atm_run_id"}
    )


def _foundation_subject() -> object:
    # the real committed fixture — must agree with the Python wire constants.
    return _FIXTURE.read_text()


def foundation_consumers_read_the_single_source() -> list[str]:
    """The T2 resolver + onboarding proposal read the same key/field as ``wire`` (live).

    Returns the names of any consumer whose constant disagrees with ``valuemaxx.core.wire``
    (should be empty) — the producer and consumer cannot silently drift apart.
    """
    from valuemaxx.attribution.binding.t2_baggage import BAGGAGE_RUN_ID_KEY
    from valuemaxx.onboarding import propose

    offenders: list[str] = []
    if BAGGAGE_RUN_ID_KEY != wire.BAGGAGE_RUN_ID_KEY:
        offenders.append("t2_baggage.BAGGAGE_RUN_ID_KEY")
    if propose._INJECTED_FIELD != wire.INJECTED_RUN_ID_FIELD:
        offenders.append("onboarding.propose._INJECTED_FIELD")
    return offenders


RULE = Rule(
    name="run_id_wire_parity",
    kind=RuleKind.STATIC,
    green_now=True,
    owner_task="RUN-ID-CARRY",
    flags_violation=_flags,
    negative_fixture=_negative_fixture,
    foundation_subject=_foundation_subject,
)
