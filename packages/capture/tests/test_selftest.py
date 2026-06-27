"""PG2 — version self-test: warn loudly + degrade granularity, never silent (§5.2).

At init the SDK checks the installed openai/anthropic/httpx versions against a
known-good range and confirms the transport hook is present. Out-of-range or an
absent/ineffective hook → a loud warning NAMING the package+version and a graceful
downgrade to ``per_call`` granularity (tagged), never a silent wrong-granularity
capture.
"""

from __future__ import annotations

from valuemaxx.capture.selftest import KNOWN_GOOD, SelfTestResult, version_selftest
from valuemaxx.core.enums import CaptureGranularity


def test_in_range_versions_keep_per_attempt() -> None:
    """test_in_range_versions_keep_per_attempt: compatible versions -> per_attempt, no warning."""
    installed = {pkg: rng.known_good_example for pkg, rng in KNOWN_GOOD.items()}
    result = version_selftest(installed_versions=installed, hook_present=True)
    assert result.granularity is CaptureGranularity.PER_ATTEMPT
    assert result.warnings == ()


def test_out_of_range_warns_and_degrades() -> None:
    """test_out_of_range_warns_and_degrades: an out-of-range version -> per_call + named warning."""
    installed = {pkg: rng.known_good_example for pkg, rng in KNOWN_GOOD.items()}
    installed["httpx"] = "0.1.0"  # far below the supported floor
    result = version_selftest(installed_versions=installed, hook_present=True)
    assert result.granularity is CaptureGranularity.PER_CALL
    assert any("httpx" in w and "0.1.0" in w for w in result.warnings)


def test_absent_hook_warns_and_degrades() -> None:
    """test_absent_hook_warns_and_degrades: an ineffective patch -> per_call + warning."""
    installed = {pkg: rng.known_good_example for pkg, rng in KNOWN_GOOD.items()}
    result = version_selftest(installed_versions=installed, hook_present=False)
    assert result.granularity is CaptureGranularity.PER_CALL
    assert any("hook" in w.lower() for w in result.warnings)


def test_absent_package_is_not_an_error() -> None:
    """test_absent_package_is_not_an_error: an un-installed SDK is skipped, not a failure."""
    # only httpx installed (no openai/anthropic) -> still per_attempt if httpx is fine
    installed = {"httpx": KNOWN_GOOD["httpx"].known_good_example}
    result = version_selftest(installed_versions=installed, hook_present=True)
    assert result.granularity is CaptureGranularity.PER_ATTEMPT
    assert result.warnings == ()


def test_result_is_immutable_record() -> None:
    """test_result_is_immutable_record: SelfTestResult carries granularity + warnings tuple."""
    result = SelfTestResult(granularity=CaptureGranularity.PER_ATTEMPT, warnings=())
    assert result.granularity is CaptureGranularity.PER_ATTEMPT
    assert result.warnings == ()
