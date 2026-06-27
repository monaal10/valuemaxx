"""wire_semconv_parity — the committed fixture matches the Python semconv (GREEN; Py half).

The OTLP key set is a single source of truth shared across languages (H3). The
Python half of the parity contract: the committed ``tests/wire_contract/
semconv_keys.json`` fixture must be exactly ``{"keys": sorted(ALL_KEYS)}`` from
``valuemaxx.capture.otlp.semconv``, and must use the standard key names (never the
``PROMPT``/``COMPLETION`` style that drifts from the OpenTelemetry GenAI semconv).
The TS half (decoding a TS-emitted span) lands with G3-OTLP-CONTRACT; this rule
owns and turns GREEN the Python side.

``flags_violation`` flags a subject that either uses a non-standard key name OR is
a fixture JSON whose key set disagrees with the Python ``ALL_KEYS``. The negative
fixture is a drifted key; the foundation subject is the committed fixture, which
agrees with the Python constants.
"""

from __future__ import annotations

import json

from valuemaxx.capture.otlp import semconv

from tests.conformance.astutil import REPO_ROOT
from tests.conformance.rulebase import Rule, RuleKind

_BAD_KEY_MARKERS: tuple[str, ...] = ("PROMPT", "COMPLETION")
_FIXTURE = REPO_ROOT / "tests" / "wire_contract" / "semconv_keys.json"


def _flags(subject: object) -> bool:
    assert isinstance(subject, str)
    # 1) a non-standard (drifted) key name is always a violation.
    if any(marker in subject for marker in _BAD_KEY_MARKERS):
        return True
    # 2) if the subject is fixture-shaped JSON, its key set must equal Python ALL_KEYS.
    try:
        payload = json.loads(subject)
    except (json.JSONDecodeError, ValueError):
        return False
    if isinstance(payload, dict) and "keys" in payload:
        return set(payload["keys"]) != set(semconv.ALL_KEYS)
    return False


def _negative_fixture() -> object:
    # a drifted fixture: a PROMPT-style key that isn't in the standard semconv
    return json.dumps({"keys": ["gen_ai.usage.PROMPT_tokens"]})


def _foundation_subject() -> object:
    # the real committed fixture — must agree with the Python semconv constants.
    return _FIXTURE.read_text()


RULE = Rule(
    name="wire_semconv_parity",
    kind=RuleKind.STATIC,
    green_now=True,
    owner_task="OTLP-CONTRACT",  # TS half lands at G3; Python half is green here
    flags_violation=_flags,
    negative_fixture=_negative_fixture,
    foundation_subject=_foundation_subject,
)
