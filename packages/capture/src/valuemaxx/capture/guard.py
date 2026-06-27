"""PG0 — the fail-open guard: instrumentation NEVER throws into the host call path.

The single most important property of the capture SDK (H9, §5.1): *an
instrumentation library that throws into ``create()`` is an adoption-killer.*
Therefore every line of our telemetry work runs inside :func:`guard`, which
swallows **only our own** exceptions (catching ``Exception`` — never
``BaseException``, so ``KeyboardInterrupt``/``SystemExit`` still propagate),
logs them, and counts a drop.

The host call is **outside** the guard by construction. The wrapper does:

    result = wrapped(*args, **kwargs)          # host call — NOT guarded
    with guard(logger, drop_counter=drops):    # only our capture is guarded
        _capture_from(result)

so the host's own exception is never caught here and the caller always sees the
real result (or the real error). The conformance rule ``sdk_fails_open`` asserts
this structurally.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator
    from logging import Logger


class DropCounter:
    """A monotonic counter of dropped/suppressed telemetry events (never resets).

    The dropped-event count is itself a reported signal (§5.1): when ingest is
    unavailable or our capture errors, we drop-and-count rather than block or
    crash the host, and surface the count so silent data loss is impossible.
    """

    __slots__ = ("_count",)

    def __init__(self) -> None:
        self._count = 0

    @property
    def count(self) -> int:
        """The number of telemetry events dropped/suppressed so far."""
        return self._count

    def increment(self) -> None:
        """Record one dropped/suppressed telemetry event."""
        self._count += 1


@contextmanager
def guard(logger: Logger, *, drop_counter: DropCounter) -> Generator[None]:
    """Run a block of OUR telemetry work fail-open: swallow our errors, count a drop.

    Catches ``Exception`` (so ordinary capture failures are suppressed) but lets
    ``BaseException`` (``KeyboardInterrupt``, ``SystemExit``) propagate — those
    are control-flow signals, not telemetry errors. Every suppressed error is
    logged with its traceback (never silent) and counted on ``drop_counter``.

    The host call MUST live outside this context manager; see the module docstring.
    """
    try:
        yield
    except Exception:
        drop_counter.increment()
        logger.warning("valuemaxx capture suppressed an internal error (fail-open)", exc_info=True)


__all__ = ["DropCounter", "guard"]
