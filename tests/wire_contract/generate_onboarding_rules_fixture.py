"""Regenerate the cross-language onboarding rules fixture.

Run by CI before the TypeScript job: regenerate ``onboarding_rules.json`` from
``valuemaxx.onboarding.rules`` (the single source of truth) and then
``git diff --exit-code`` — any drift between the Python rule constants and the committed
fixture (which the TS scanner consumes) fails the build.

Usage:
    uv run python tests/wire_contract/generate_onboarding_rules_fixture.py
"""

from __future__ import annotations

from pathlib import Path

from valuemaxx.onboarding import rules

FIXTURE_PATH = Path(__file__).resolve().parent / "onboarding_rules.json"


def main() -> None:
    """Write the fixture from the single-source onboarding rule constants."""
    rules.generate_onboarding_rules_fixture(FIXTURE_PATH)


if __name__ == "__main__":
    main()
