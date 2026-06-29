"""Inject the single-wheel bundle config into the published ``valuemaxx`` package.

valuemaxx ships ONE PyPI package (``valuemaxx``) that bundles every ``valuemaxx.*``
module, so ``pip install valuemaxx`` is a self-contained SDK and ``pip install
valuemaxx[cli]`` adds the CLI/backend — without publishing ~15 separate internal
packages. But the bundling uses hatchling ``force-include``, and uv's *editable* install
materializes force-included dirs as STATIC COPIES that shadow the live editable
workspace packages (``valuemaxx-server`` -> ``apps/server`` …), breaking dev: an edit
under ``apps/`` would not take effect without a re-sync.

So the bundle is **release-only**: the dev ``sdks/python/pyproject.toml`` ships just
``valuemaxx.sdk`` (clean editable installs), and this script appends the
``[tool.hatch.build.targets.wheel.force-include]`` table to that pyproject right before
``uv build`` in the release workflow. Idempotent; ``--check`` verifies the dev pyproject
is in its clean (un-bundled) state, which CI can assert so the bundle never leaks into a
committed file.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PYPROJECT = _REPO_ROOT / "sdks" / "python" / "pyproject.toml"

# The marker line the bundle table is appended under (also how --check detects it).
_MARKER = "[tool.hatch.build.targets.wheel.force-include]"

# Every valuemaxx.* module to bundle into the published wheel, mapped from its sibling
# workspace package's src dir (relative to sdks/python) to its path inside the wheel.
_BUNDLE: tuple[tuple[str, str], ...] = (
    ("../../packages/core/src/valuemaxx/core", "valuemaxx/core"),
    ("../../packages/capabilities/src/valuemaxx/capabilities", "valuemaxx/capabilities"),
    ("../../packages/capture/src/valuemaxx/capture", "valuemaxx/capture"),
    ("../../packages/outcomes/src/valuemaxx/outcomes", "valuemaxx/outcomes"),
    ("../../packages/attribution/src/valuemaxx/attribution", "valuemaxx/attribution"),
    ("../../packages/reconciliation/src/valuemaxx/reconciliation", "valuemaxx/reconciliation"),
    ("../../packages/allocation/src/valuemaxx/allocation", "valuemaxx/allocation"),
    ("../../packages/metrics/src/valuemaxx/metrics", "valuemaxx/metrics"),
    ("../../packages/eval/src/valuemaxx/eval", "valuemaxx/eval"),
    ("../../packages/onboarding/src/valuemaxx/onboarding", "valuemaxx/onboarding"),
    ("../../packages/store/src/valuemaxx/store", "valuemaxx/store"),
    (
        "../../apps/agent_integrability/src/valuemaxx/agent_integrability",
        "valuemaxx/agent_integrability",
    ),
    ("../../apps/api/src/valuemaxx/api", "valuemaxx/api"),
    ("../../apps/mcp/src/valuemaxx/mcp", "valuemaxx/mcp"),
    ("../../apps/notify/src/valuemaxx/notify", "valuemaxx/notify"),
    ("../../apps/server/src/valuemaxx/server", "valuemaxx/server"),
    ("../../apps/cli/src/valuemaxx/cli", "valuemaxx/cli"),
)


def _bundle_block() -> str:
    lines = [_MARKER]
    lines += [f'"{src}" = "{dst}"' for src, dst in _BUNDLE]
    return "\n".join(lines) + "\n"


def inject() -> None:
    """Append the force-include bundle table to the SDK pyproject (idempotent)."""
    text = _PYPROJECT.read_text()
    if _MARKER in text:
        return  # already bundled — idempotent
    if not text.endswith("\n"):
        text += "\n"
    _PYPROJECT.write_text(text + "\n" + _bundle_block())


def check() -> int:
    """Return 0 iff the committed pyproject is in its clean (un-bundled) dev state."""
    if _MARKER in _PYPROJECT.read_text():
        sys.stderr.write(
            "sdks/python/pyproject.toml contains the release-only bundle table; "
            "it must NOT be committed (it breaks editable dev). Remove it.\n"
        )
        return 1
    return 0


def main(argv: list[str]) -> int:
    if "--check" in argv:
        return check()
    inject()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
