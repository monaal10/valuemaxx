"""PG0 — the fail-open guard MUST NOT throw into the host call path (§5.1, H9).

``guard`` swallows ONLY our own telemetry exceptions and counts a drop; it never
catches the host's exception (the host call is OUTSIDE the guard by construction).
"""

from __future__ import annotations

import logging

import pytest
from valuemaxx.capture.guard import DropCounter, guard
from valuemaxx.core.errors import CaptureError


def test_guard_suppresses_our_telemetry_exception() -> None:
    """test_guard_suppresses_our_telemetry_exception: our error inside the guard never escapes."""
    drops = DropCounter()
    logger = logging.getLogger("test.guard")
    with guard(logger, drop_counter=drops):
        raise CaptureError("emit failed")  # our telemetry error
    # the guard swallowed it and counted a drop — control reaches here
    assert drops.count == 1


def test_guard_logs_the_suppressed_exception(caplog: pytest.LogCaptureFixture) -> None:
    """test_guard_logs_the_suppressed_exception: a swallowed error is logged, never silent."""
    drops = DropCounter()
    logger = logging.getLogger("test.guard.log")
    with (
        caplog.at_level(logging.WARNING, logger="test.guard.log"),
        guard(logger, drop_counter=drops),
    ):
        raise CaptureError("boom")
    assert any("boom" in rec.getMessage() or rec.exc_info for rec in caplog.records)


def _raise_keyboard_interrupt(logger: logging.Logger, drops: DropCounter) -> None:
    with guard(logger, drop_counter=drops):
        raise KeyboardInterrupt


def test_guard_does_not_catch_keyboard_interrupt() -> None:
    """test_guard_does_not_catch_keyboard_interrupt: never swallow BaseException-class signals."""
    drops = DropCounter()
    logger = logging.getLogger("test.guard.kbd")
    with pytest.raises(KeyboardInterrupt):
        _raise_keyboard_interrupt(logger, drops)
    assert drops.count == 0  # a control-flow signal is not a dropped telemetry event


def _host_then_capture(logger: logging.Logger, drops: DropCounter, captured: list[str]) -> None:
    # mirrors the wrapper: host call OUTSIDE the guard, only capture INSIDE it
    result = _failing_host_call()
    with guard(logger, drop_counter=drops):
        captured.append(result)


def _failing_host_call() -> str:
    raise ValueError("the host's own error")


def test_guard_does_not_swallow_host_exception_by_design() -> None:
    """test_guard_does_not_swallow_host_exception_by_design: host call sits OUTSIDE the guard.

    The fail-open contract is structural: the host call runs first and its result
    (or exception) is what the caller sees; only the *capture* of that result runs
    inside the guard. The host's own exception therefore propagates to the caller.
    """
    drops = DropCounter()
    logger = logging.getLogger("test.guard.host")
    captured: list[str] = []

    with pytest.raises(ValueError, match="the host's own error"):
        _host_then_capture(logger, drops, captured)

    assert captured == []
    assert drops.count == 0  # we never even reached the guard


def test_drop_counter_increments() -> None:
    drops = DropCounter()
    assert drops.count == 0
    drops.increment()
    drops.increment()
    assert drops.count == 2
