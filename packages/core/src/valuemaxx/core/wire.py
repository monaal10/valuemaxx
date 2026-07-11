"""The cross-language run_id carry contract — T2 baggage key + T3 injected field.

Both SDKs (Python + TypeScript) automate deterministic binding by stamping the active
run_id onto an outbound channel: W3C baggage for a live service hop (T2), and a named
external call's kwargs for a delayed webhook round-trip (T3). The *key* they stamp under
must be identical across languages and identical to what the attribution cascade reads
back, or a carried run_id is silently dropped.

This module is the single source of truth for those two constants:

* :data:`BAGGAGE_RUN_ID_KEY` — the W3C-baggage key the T2 producer stamps and the
  :class:`~valuemaxx.attribution.binding.t2_baggage.BaggageResolver` reads.
* :data:`INJECTED_RUN_ID_FIELD` — the default dotted passthrough path the T3 injector
  merges run_id into, and the field onboarding proposes in ``run_id_injection``.

:func:`generate_wire_fixture` serialises both into the JSON fixture the TypeScript SDK
consumes; CI regenerates it and ``git diff --exit-code``s it, so a drift between the
Python constants and the TS copy fails the build (mirrors the semconv fixture, H3).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from pathlib import Path

BAGGAGE_RUN_ID_KEY: Final = "valuemaxx.run_id"
"""The W3C-baggage key the active run id rides across a live service hop (T2)."""

INJECTED_RUN_ID_FIELD: Final = "metadata.atm_run_id"
"""The default dotted passthrough path the run id is merged into on an outbound call (T3)."""


def generate_wire_fixture(path: Path) -> None:
    """Write ``{baggage_run_id_key, injected_run_id_field}`` to ``path`` (byte-stable).

    CI regenerates this and runs ``git diff --exit-code`` so any drift between the
    constants here and the committed fixture (and the TypeScript copy the SDK bundles)
    fails the build before the TS job runs — the two run_id producers cannot diverge.
    """
    payload = {
        "baggage_run_id_key": BAGGAGE_RUN_ID_KEY,
        "injected_run_id_field": INJECTED_RUN_ID_FIELD,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


__all__ = ["BAGGAGE_RUN_ID_KEY", "INJECTED_RUN_ID_FIELD", "generate_wire_fixture"]
