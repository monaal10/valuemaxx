"""PG2 — startup version self-test: warn loudly + degrade, never silent (§5.2, H9).

Per-attempt capture requires patching the SDK's HTTP transport, which lives in
``_base_client``/``httpx`` *below* the public ``create()``. If the installed
``openai``/``anthropic``/``httpx`` version is outside the tested range, or the
transport hook did not take effect, we must NOT silently capture the wrong
granularity. Instead we **warn loudly, naming the package and version**, and
gracefully **degrade to ``per_call``** capture (tagged on every CostEvent).

``version_selftest`` is pure and injectable (the installed versions + hook-present
flag are passed in) so it is deterministic under test (AGENTS.md §1).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from valuemaxx.core.enums import CaptureGranularity

if TYPE_CHECKING:
    from collections.abc import Mapping

_LOGGER = logging.getLogger("valuemaxx.capture.selftest")


def _parse(version: str) -> tuple[int, ...]:
    """Parse a dotted version into a comparable integer tuple (best-effort, lenient).

    Non-numeric trailing segments (rc/dev/post suffixes) are truncated at the first
    non-digit so ``0.28.1rc1`` compares as ``(0, 28, 1)`` — good enough for a
    floor/ceiling range check, and it never raises on an odd version string.
    """
    parts: list[int] = []
    for segment in version.split("."):
        digits = ""
        for ch in segment:
            if ch.isdigit():
                digits += ch
            else:
                break
        if digits == "":
            break
        parts.append(int(digits))
    return tuple(parts)


@dataclass(frozen=True, slots=True)
class SupportedRange:
    """The inclusive-floor / exclusive-ceiling supported version window for a package."""

    floor: str
    ceiling: str
    known_good_example: str

    def contains(self, version: str) -> bool:
        """True if ``version`` is in [floor, ceiling)."""
        v = _parse(version)
        return _parse(self.floor) <= v < _parse(self.ceiling)


# The tested-compatible ranges. These are conservative windows we have a transport
# hook for; outside them we degrade to per_call rather than guess.
KNOWN_GOOD: Mapping[str, SupportedRange] = {
    "httpx": SupportedRange(floor="0.27.0", ceiling="1.0.0", known_good_example="0.28.1"),
    "openai": SupportedRange(floor="1.0.0", ceiling="2.0.0", known_good_example="1.50.0"),
    "anthropic": SupportedRange(floor="0.30.0", ceiling="1.0.0", known_good_example="0.40.0"),
}


@dataclass(frozen=True, slots=True)
class SelfTestResult:
    """The outcome of the startup self-test: the effective granularity + any warnings."""

    granularity: CaptureGranularity
    warnings: tuple[str, ...]


def version_selftest(
    *, installed_versions: Mapping[str, str], hook_present: bool
) -> SelfTestResult:
    """Check installed versions + hook presence; degrade to per_call on any problem.

    ``installed_versions`` maps package name -> version string for the SDKs actually
    importable in the host (absent packages are simply skipped — not an error).
    Returns :class:`SelfTestResult`; every warning names the offending package and
    version (or the missing hook) so the degrade is never silent.
    """
    warnings: list[str] = []
    for pkg, version in installed_versions.items():
        rng = KNOWN_GOOD.get(pkg)
        if rng is None:
            continue
        if not rng.contains(version):
            warnings.append(
                f"{pkg} {version} is outside the tested range "
                f"[{rng.floor}, {rng.ceiling}); degrading capture to per_call"
            )
    if not hook_present:
        warnings.append(
            "transport hook did not take effect (the patch is ineffective); "
            "degrading capture to per_call — capture is NOT silently empty"
        )
    granularity = CaptureGranularity.PER_ATTEMPT if not warnings else CaptureGranularity.PER_CALL
    for w in warnings:
        _LOGGER.warning("valuemaxx capture self-test: %s", w)
    return SelfTestResult(granularity=granularity, warnings=tuple(warnings))


__all__ = ["KNOWN_GOOD", "SelfTestResult", "SupportedRange", "version_selftest"]
