"""Regenerate the cross-language run_id carry-contract fixture (T2 baggage + T3 inject).

Run by CI before the TypeScript job: regenerate ``run_id_wire.json`` from
``valuemaxx.core.wire`` and then ``git diff --exit-code`` — any drift between the Python
constants (the single source) and the committed fixture the TS SDK bundles fails the
build. Writes BOTH the wire-contract copy and the copy vendored into the npm package so
the published SDK carries the identical key/field the backend cascade reads.

Usage:
    uv run python tests/wire_contract/generate_run_id_wire_fixture.py
"""

from __future__ import annotations

from pathlib import Path

from valuemaxx.core import wire

_HERE = Path(__file__).resolve().parent
FIXTURE_PATH = _HERE / "run_id_wire.json"
# The TS SDK bundles its own copy so the published package is self-contained.
TS_COPY_PATH = _HERE.parent.parent / "sdks" / "typescript" / "src" / "run_id_wire.json"


def main() -> None:
    """Write the fixture (and the TS SDK copy) from the single-source wire constants."""
    wire.generate_wire_fixture(FIXTURE_PATH)
    wire.generate_wire_fixture(TS_COPY_PATH)


if __name__ == "__main__":
    main()
