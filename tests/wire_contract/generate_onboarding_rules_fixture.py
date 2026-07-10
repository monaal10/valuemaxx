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

_HERE = Path(__file__).resolve().parent
FIXTURE_PATH = _HERE / "onboarding_rules.json"
# The TS SDK bundles its own copy so the published npm package (which does not include
# tests/) can read the rules at runtime. Both are generated from the same single source, so
# CI's `git diff --exit-code` on either catches drift.
TS_EMBEDDED_PATH = (
    _HERE.parents[1] / "sdks" / "typescript" / "src" / "onboarding" / "onboarding_rules.json"
)


def main() -> None:
    """Write the fixture (wire-contract copy + the TS SDK's bundled copy) from the source."""
    rules.generate_onboarding_rules_fixture(FIXTURE_PATH)
    if TS_EMBEDDED_PATH.parent.exists():
        rules.generate_onboarding_rules_fixture(TS_EMBEDDED_PATH)


if __name__ == "__main__":
    main()
