"""The onboarding rules are single-source and the fixture never drifts.

``valuemaxx.onboarding.rules`` is the one place the cross-language SCAN detection rules
live; the Python scanner imports the constants and the TypeScript scanner reads the
generated ``onboarding_rules.json``. These tests lock in that (a) the Python scanners
actually source their rules from this module (so a change here changes both), and (b) the
committed fixture matches ``rules.as_dict()`` byte-for-byte — the same guard CI runs.
"""

from __future__ import annotations

import json
from pathlib import Path

from valuemaxx.onboarding import rules, scan, ts_scan

_FIXTURE = Path(__file__).resolve().parents[3] / "tests" / "wire_contract" / "onboarding_rules.json"


def test_committed_fixture_matches_the_single_source() -> None:
    """The committed onboarding_rules.json equals rules.as_dict() (CI's git-diff guard)."""
    committed = json.loads(_FIXTURE.read_text())
    assert committed == rules.as_dict()


def test_python_scanners_source_rules_from_the_single_module() -> None:
    """The Python TS-scanner + codebase scanner use the rules module, not local copies."""
    # TS scanner rule sets are exactly the rules module's (order-insensitive).
    assert frozenset(rules.TS_LLM_CALLS) == ts_scan._TS_LLM_CALLS
    assert frozenset(rules.TS_PROVIDER_CALLS) == ts_scan._TS_PROVIDER_CALLS
    assert frozenset(rules.ORM_WRITES) == ts_scan._TS_ORM_WRITES
    assert ts_scan._TS_MARK_PREFIXES == rules.MARK_PREFIXES
    assert ts_scan.TS_SUFFIXES == rules.TS_SUFFIXES
    # The codebase scanner's shared rules come from the module too.
    assert frozenset(rules.ECHOING_SYSTEMS) == scan.ECHOING_SYSTEMS
    assert frozenset(rules.IGNORED_DIRS) == scan._IGNORED_DIRS


def test_fixture_shape_is_complete() -> None:
    """The fixture carries every rule the TS scanner needs (a missing key would break it)."""
    d = rules.as_dict()
    for key in (
        "ts_llm_calls",
        "ts_provider_calls",
        "orm_writes",
        "mark_prefixes",
        "ts_suffixes",
        "echoing_systems",
        "external_systems",
        "ignored_dirs",
        "entity_id_exclusions",
    ):
        assert key in d, f"onboarding rules fixture is missing {key!r}"
    # sanity: the Vercel verbs and the TS suffixes are present.
    llm_calls = d["ts_llm_calls"]
    suffixes = d["ts_suffixes"]
    assert isinstance(llm_calls, list)
    assert isinstance(suffixes, list)
    assert "generateText" in llm_calls
    assert ".ts" in suffixes
