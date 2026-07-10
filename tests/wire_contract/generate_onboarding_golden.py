"""Regenerate the cross-language onboarding golden output.

Runs the Python onboarding pipeline (scan -> propose -> render) on the shared fixture repo
(``onboarding_fixture/``) and writes the PARSED ``outcomes.yaml`` to ``onboarding_golden.json``.
CI regenerates this and ``git diff --exit-code``s it (Python-side drift guard); the TS golden
parity test asserts the TS pipeline produces the same parsed output on the same fixture
(TS-side drift guard). Together they pin the two pipelines to identical proposals.

Usage:
    uv run python tests/wire_contract/generate_onboarding_golden.py
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from valuemaxx.onboarding.propose import build_proposal
from valuemaxx.onboarding.render import render_outcomes_yaml
from valuemaxx.onboarding.scan import scan_codebase

_HERE = Path(__file__).resolve().parent
FIXTURE = _HERE / "onboarding_fixture"
GOLDEN = _HERE / "onboarding_golden.json"

# The system-owned signal mapper (a bare external write is only action_attempted; a status
# transition / mark / ORM write / webhook confirms an outcome). Mirrors the CLI's mapper and
# the TS CONFIRMING set — the single behavioural contract both pipelines share.
_CONFIRMING = frozenset({"status_setter", "mark_function", "orm_write", "webhook"})


class _SignalMapper:
    def map_signal(self, *, match_kind: str, declared: str) -> str:
        _ = declared  # advisory only; the system owns the result
        return "outcome_confirmed" if match_kind in _CONFIRMING else "action_attempted"


def main() -> None:
    """Write the golden parsed outcomes.yaml from the Python pipeline on the fixture."""
    scan = scan_codebase(FIXTURE)
    proposal = build_proposal(scan, signal_mapper=_SignalMapper())
    parsed = yaml.safe_load(render_outcomes_yaml(proposal))
    GOLDEN.write_text(json.dumps(parsed, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
