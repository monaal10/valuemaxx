"""G1-CORE-WIRE: the cross-language run_id carry contract (T2 baggage + T3 inject).

``wire.py`` is the single source of truth for the two constants both SDKs stamp the
active run_id onto: the W3C-baggage key (T2) and the default injected field (T3).
Attribution reads the baggage key; onboarding proposes the injected field; both SDKs
produce them. Centralising them here — and diffing a generated JSON fixture against a
TS copy in CI — is what stops the Python and TypeScript producers from drifting.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from valuemaxx.core import wire

if TYPE_CHECKING:
    from pathlib import Path


def test_baggage_key_is_the_w3c_run_id_key() -> None:
    """test_baggage_key_is_the_w3c_run_id_key: the T2 baggage key is stable + namespaced."""
    assert wire.BAGGAGE_RUN_ID_KEY == "valuemaxx.run_id"


def test_injected_field_is_dotted_metadata_path() -> None:
    """test_injected_field_is_dotted_metadata_path: the T3 default inject path is dotted."""
    assert wire.INJECTED_RUN_ID_FIELD == "metadata.atm_run_id"
    # a dotted passthrough path (container.leaf), never a bare leaf — the injector walks it.
    assert "." in wire.INJECTED_RUN_ID_FIELD


def test_attribution_baggage_resolver_reads_the_same_key() -> None:
    """test_attribution_baggage_resolver_reads_the_same_key: T2 consumer + producer agree.

    The cascade's T2 resolver must read the exact key the producer stamps, or a
    baggage-carried run_id is silently dropped. One constant, both sides.
    """
    from valuemaxx.attribution.binding.t2_baggage import BAGGAGE_RUN_ID_KEY

    assert BAGGAGE_RUN_ID_KEY == wire.BAGGAGE_RUN_ID_KEY


def test_onboarding_proposes_the_same_injected_field() -> None:
    """test_onboarding_proposes_the_same_injected_field: proposal + runtime default agree.

    onboard writes ``run_id_injection.target_field`` into outcomes.yaml; the runtime
    injector defaults to the same path. Sourced from one constant so they cannot drift.
    """
    from valuemaxx.onboarding import propose

    assert propose._INJECTED_FIELD == wire.INJECTED_RUN_ID_FIELD


def test_generate_wire_fixture_matches_the_constants(tmp_path: Path) -> None:
    """test_generate_wire_fixture_matches_the_constants: the fixture serialises the source.

    The generated JSON the TS SDK consumes is exactly ``{baggage_run_id_key,
    injected_run_id_field}`` from the constants — byte-for-byte, sorted, trailing NL.
    """
    out = tmp_path / "run_id_wire.json"
    wire.generate_wire_fixture(out)
    payload = json.loads(out.read_text())
    assert payload == {
        "baggage_run_id_key": wire.BAGGAGE_RUN_ID_KEY,
        "injected_run_id_field": wire.INJECTED_RUN_ID_FIELD,
    }
    # deterministic serialisation (sorted keys, 2-space indent, trailing newline).
    assert out.read_text() == json.dumps(payload, indent=2, sort_keys=True) + "\n"
