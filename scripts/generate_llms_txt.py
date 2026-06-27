#!/usr/bin/env python3
"""Regenerate the root llms.txt from the live capability registry — the single
source of truth, so the agent-facing capability listing can never drift. CI runs
this + `git diff --exit-code` (mirroring the OTLP semconv-parity pattern)."""

from __future__ import annotations

from pathlib import Path

from valuemaxx.agent_integrability.discovery import build_default_registry
from valuemaxx.agent_integrability.llms_txt import generate_llms_txt

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    (ROOT / "llms.txt").write_text(generate_llms_txt(build_default_registry()))
    print(f"wrote {ROOT / 'llms.txt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
