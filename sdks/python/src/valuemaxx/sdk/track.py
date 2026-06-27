"""``track.run`` — establish the ambient run_id for cost binding (§5.1, H2).

The capture transport patch reads ``active_run_id`` off a contextvar; ``track.run``
is the one-liner the host wraps around an agent run so every LLM call inside binds
to it. The prior value is restored on exit (including on exception), so nesting and
error paths never leak a stale run id.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

from valuemaxx.core.context import active_run_id
from valuemaxx.core.ids import RunId

if TYPE_CHECKING:
    from collections.abc import Generator


@contextmanager
def run(*, run_id: str) -> Generator[RunId]:
    """Bind ``run_id`` as the ambient run for the duration of the ``with`` block.

    Yields the typed :class:`~valuemaxx.core.ids.RunId`. The previous ambient value
    is restored on exit, even if the body raises.
    """
    typed = RunId(run_id)
    token = active_run_id.set(typed)
    try:
        yield typed
    finally:
        active_run_id.reset(token)


__all__ = ["run"]
