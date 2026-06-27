"""Regenerate the cross-language OTLP semconv key fixture (H3).

Run by CI before the TypeScript job: regenerate ``semconv_keys.json`` from
``valuemaxx.capture.otlp.semconv.ALL_KEYS`` and then ``git diff --exit-code`` —
any drift between the Python constants and the committed fixture (which the TS
side consumes) fails the build. ``semconv.py`` is the single source of truth; this
script only serializes it.

Usage:
    uv run python tests/wire_contract/generate_semconv_fixture.py
"""

from __future__ import annotations

from pathlib import Path

from valuemaxx.capture.otlp import semconv

FIXTURE_PATH = Path(__file__).resolve().parent / "semconv_keys.json"


def main() -> None:
    """Write the fixture from the single-source semconv constants."""
    semconv.generate_semconv_fixture(FIXTURE_PATH)


if __name__ == "__main__":
    main()
