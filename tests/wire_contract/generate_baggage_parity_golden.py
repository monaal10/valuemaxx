"""Regenerate the cross-language T2 baggage-encoding parity golden.

Both SDKs' T2 producers stamp the active run_id onto the outbound W3C ``baggage`` header.
They are the same mechanism expressed in each language's native wrap/context API — but
"the same by inspection" is fragile. This pins it: a fixed set of input vectors (existing
baggage members, absent header, a stale run_id to replace, blank) is driven through the
REAL Python producer (:func:`~valuemaxx.outcomes.instrument.baggage.install_run_id_baggage`),
and the resulting ``baggage`` header string for each is written to ``baggage_parity_golden.json``.

CI regenerates this and ``git diff --exit-code``s it (Python-side drift guard); the TS
``baggage`` parity test asserts the TS producer emits the identical string for the identical
vectors (TS-side drift guard). Together they pin the two producers to one byte-exact encoding.

Usage:
    uv run python tests/wire_contract/generate_baggage_parity_golden.py
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from typing import cast

from valuemaxx.core import RunId, active_run_id
from valuemaxx.outcomes.instrument.baggage import install_run_id_baggage

_HERE = Path(__file__).resolve().parent
GOLDEN = _HERE / "baggage_parity_golden.json"

# The shared input vectors. Each is (name, run_id, incoming `headers` kwarg). The TS parity
# test drives the identical vectors; keep this list and the TS copy in lockstep by contract.
VECTORS: tuple[tuple[str, str, dict[str, object]], ...] = (
    ("no_headers", "run-1", {}),
    ("empty_baggage", "run-2", {"baggage": ""}),
    ("existing_member", "run-3", {"baggage": "team=payments"}),
    ("multiple_members", "run-4", {"baggage": "team=payments,region=us"}),
    ("stale_run_id_replaced", "run-5", {"baggage": "valuemaxx.run_id=stale,team=x"}),
    ("unrelated_headers_only", "run-6", {"authorization": "Bearer x"}),
)


def _baggage_for(run_id: str, headers: dict[str, object]) -> str:
    """Drive one vector through the REAL Python producer; return the emitted baggage string."""
    mod = types.ModuleType("baggage_parity_probe")

    class Probe:
        @staticmethod
        def request(**kwargs: object) -> dict[str, object]:
            return {"received": kwargs}

    mod.Probe = Probe  # type: ignore[attr-defined]
    sys.modules["baggage_parity_probe"] = mod
    try:
        install_run_id_baggage(["baggage_parity_probe.Probe.request"])
        token = active_run_id.set(RunId(run_id))
        try:
            result = mod.Probe.request(url="u", headers=dict(headers))
        finally:
            active_run_id.reset(token)
    finally:
        sys.modules.pop("baggage_parity_probe", None)
    received = cast("dict[str, object]", result["received"])
    out_headers = cast("dict[str, object]", received["headers"])
    return cast("str", out_headers["baggage"])


def main() -> None:
    """Write the golden {vector_name: emitted baggage string} from the Python producer."""
    golden = {name: _baggage_for(run_id, headers) for name, run_id, headers in VECTORS}
    GOLDEN.write_text(json.dumps(golden, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
