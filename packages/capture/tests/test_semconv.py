"""PG4 — the OTLP semconv module is the SINGLE source of OTLP keys (§5.2, H3).

Every wire key is a module constant in ``valuemaxx.capture.otlp.semconv``: the
standard ``gen_ai.*`` keys plus the ``ai_margin.*`` extensions (cache classes,
reasoning, run/attempt/tenant ids, provenance, granularity, cost, streaming
flags). ``ALL_KEYS`` is the authoritative set, and ``generate_semconv_fixture``
writes ``{"keys": sorted(ALL_KEYS)}`` — the byte-for-byte cross-language contract
the TS side consumes.
"""

from __future__ import annotations

import json
from pathlib import Path

from valuemaxx.capture.otlp import semconv

_FIXTURE = Path(__file__).resolve().parents[3] / "tests" / "wire_contract" / "semconv_keys.json"


def test_all_keys_is_non_empty_and_unique() -> None:
    """test_all_keys_is_non_empty_and_unique: ALL_KEYS is a populated, duplicate-free set."""
    assert semconv.ALL_KEYS
    assert len(semconv.ALL_KEYS) == len(set(semconv.ALL_KEYS))


def test_standard_gen_ai_keys_present() -> None:
    """test_standard_gen_ai_keys_present: the standard gen_ai.* keys are modelled."""
    assert semconv.GEN_AI_SYSTEM == "gen_ai.system"
    assert semconv.GEN_AI_REQUEST_MODEL == "gen_ai.request.model"
    assert semconv.GEN_AI_USAGE_INPUT_TOKENS == "gen_ai.usage.input_tokens"
    assert semconv.GEN_AI_USAGE_OUTPUT_TOKENS == "gen_ai.usage.output_tokens"


def test_ai_margin_extension_keys_present() -> None:
    """test_ai_margin_extension_keys_present: valuemaxx extensions are namespaced ai_margin."""
    extensions = {
        semconv.AI_MARGIN_CACHE_READ,
        semconv.AI_MARGIN_CACHE_WRITE_5M,
        semconv.AI_MARGIN_CACHE_WRITE_1H,
        semconv.AI_MARGIN_REASONING,
        semconv.AI_MARGIN_RUN_ID,
        semconv.AI_MARGIN_ATTEMPT_ID,
        semconv.AI_MARGIN_TENANT_ID,
        semconv.AI_MARGIN_PROVENANCE,
        semconv.AI_MARGIN_CAPTURE_GRANULARITY,
        semconv.AI_MARGIN_COST_USD,
        semconv.AI_MARGIN_IS_STREAMING,
        semconv.AI_MARGIN_PARTIAL_RECOVERED,
    }
    for key in extensions:
        assert key.startswith("ai_margin."), key
    assert extensions <= set(semconv.ALL_KEYS)


def test_no_uppercase_prompt_completion_keys() -> None:
    """test_no_uppercase_prompt_completion_keys: standard names, never PROMPT/COMPLETION."""
    for key in semconv.ALL_KEYS:
        assert "PROMPT" not in key
        assert "COMPLETION" not in key


def test_generate_fixture_matches_committed(tmp_path: Path) -> None:
    """test_generate_fixture_matches_committed: regenerated fixture == committed json (H3)."""
    out = tmp_path / "semconv_keys.json"
    semconv.generate_semconv_fixture(out)
    regenerated = json.loads(out.read_text())
    committed = json.loads(_FIXTURE.read_text())
    assert regenerated == committed
    assert regenerated == {"keys": sorted(semconv.ALL_KEYS)}


def test_fixture_keys_are_sorted() -> None:
    """test_fixture_keys_are_sorted: the committed fixture's keys are sorted (deterministic)."""
    committed = json.loads(_FIXTURE.read_text())
    assert committed["keys"] == sorted(committed["keys"])
