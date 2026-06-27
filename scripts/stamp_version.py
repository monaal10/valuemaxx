#!/usr/bin/env python3
"""Stamp a single version across the publishable packages — the one place release
versions are written, so pip `valuemaxx` and npm `valuemaxx` always ship the same
number (RELEASING.md). Reads the version from the `VERSION` file (or argv[1]) and
writes it into the publishable SDK manifests.

Only the **published** artifacts are stamped:
  - sdks/python/pyproject.toml  (PyPI: valuemaxx)
  - sdks/typescript/package.json (npm: valuemaxx)

Internal workspace packages stay at 0.0.0 (they are never published; the SDKs are
the public surface). Idempotent; exits non-zero if a target is missing.

Usage:
  python scripts/stamp_version.py            # read ./VERSION, stamp both SDKs
  python scripts/stamp_version.py 0.1.0      # explicit version, stamp both SDKs
  python scripts/stamp_version.py --check    # CI: assert manifests already match VERSION

This script is the SINGLE writer of the published version — nothing else edits the
SDK version fields. `--check` runs in CI so the manifests can never drift from VERSION.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


def _read_version(argv: list[str]) -> str:
    if len(argv) > 1 and argv[1] != "--check":
        version = argv[1].lstrip("v").strip()
    else:
        version = (ROOT / "VERSION").read_text().strip()
    if not _SEMVER.match(version):
        raise SystemExit(f"refusing to stamp non-semver version: {version!r}")
    return version


def _current_pyproject_version(path: Path) -> str | None:
    m = re.search(r'(?m)^version = "([^"]*)"', path.read_text())
    return m.group(1) if m else None


def _current_package_json_version(path: Path) -> str | None:
    data = json.loads(path.read_text())
    v = data.get("version")
    return v if isinstance(v, str) else None


def _check(version: str) -> int:
    """Assert both SDK manifests already declare `version`. Non-zero on drift."""
    py = ROOT / "sdks" / "python" / "pyproject.toml"
    ts = ROOT / "sdks" / "typescript" / "package.json"
    drift: list[str] = []
    if py.exists() and (cur := _current_pyproject_version(py)) != version:
        drift.append(f"  {py.relative_to(ROOT)}: {cur} != VERSION {version}")
    if ts.exists() and (cur := _current_package_json_version(ts)) != version:
        drift.append(f"  {ts.relative_to(ROOT)}: {cur} != VERSION {version}")
    if drift:
        print("version drift detected (run scripts/stamp_version.py to fix):")
        print("\n".join(drift))
        return 1
    print(f"both SDK manifests match VERSION ({version}).")
    return 0


def _stamp_pyproject(path: Path, version: str) -> None:
    if not path.exists():
        raise SystemExit(f"missing Python SDK manifest: {path}")
    text = path.read_text()
    new = re.sub(r'(?m)^version = "[^"]*"', f'version = "{version}"', text, count=1)
    path.write_text(new)
    print(f"stamped {path.relative_to(ROOT)} -> {version}")


def _stamp_package_json(path: Path, version: str) -> None:
    if not path.exists():
        raise SystemExit(f"missing TS SDK manifest: {path}")
    data = json.loads(path.read_text())
    data["version"] = version
    path.write_text(json.dumps(data, indent=2) + "\n")
    print(f"stamped {path.relative_to(ROOT)} -> {version}")


def main(argv: list[str]) -> int:
    version = _read_version(argv)
    if "--check" in argv:
        return _check(version)
    _stamp_pyproject(ROOT / "sdks" / "python" / "pyproject.toml", version)
    _stamp_package_json(ROOT / "sdks" / "typescript" / "package.json", version)
    print(f"\nboth SDKs stamped to {version} — pip and npm will ship in lockstep.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
