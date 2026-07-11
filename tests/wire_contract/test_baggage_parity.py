"""Python-side guard for the cross-language T2 baggage-encoding parity golden.

The committed ``baggage_parity_golden.json`` must equal what the REAL Python producer emits
for the shared vectors — otherwise the golden the TS parity test asserts against is stale.
This is the Python half of the drift guard (the TS half lives in
``sdks/typescript/test/baggage-parity.test.ts``); CI also regenerates + diffs the golden.
"""

from __future__ import annotations

import json
from pathlib import Path

from tests.wire_contract.generate_baggage_parity_golden import VECTORS, _baggage_for

_GOLDEN = Path(__file__).resolve().parent / "baggage_parity_golden.json"


def test_committed_golden_matches_the_python_producer() -> None:
    """The committed golden equals the live Python producer output for every vector."""
    committed = json.loads(_GOLDEN.read_text())
    live = {name: _baggage_for(run_id, headers) for name, run_id, headers in VECTORS}
    assert committed == live
