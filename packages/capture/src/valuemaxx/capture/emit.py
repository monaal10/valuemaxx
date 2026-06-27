"""PG0 — the bounded, non-blocking Emitter (§5.1, H9).

Ingest-unavailable must never block or crash the host. The Emitter buffers
:class:`~valuemaxx.core.cost.CostEvent` records in a **bounded in-memory queue**
and drains them to a :class:`~valuemaxx.core.repositories.CostEventRepository`
off the host call path.

Two fail-open behaviours:
  * **queue full** → the event is dropped and the ``dropped`` counter increments
    (never blocks, never raises);
  * **repository failure on drain** → the failure is logged and counted, never
    raised into whoever triggered the drain.

``enqueue`` performs no synchronous write — the repository is only touched on
``drain`` — so the added latency on the host call path stays near the ``<1ms``
target (§5.1). Idempotency on ``(run_id, attempt_id)`` lives in the repository
upsert (M7), so a re-drained event never double-counts.
"""

from __future__ import annotations

import logging
from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from valuemaxx.core.cost import CostEvent
    from valuemaxx.core.ids import TenantId
    from valuemaxx.core.repositories import CostEventRepository

_LOGGER = logging.getLogger("valuemaxx.capture.emit")


class Emitter:
    """A bounded, non-blocking buffer that drains CostEvents to a repository.

    Args:
        repository: the cost-event store to drain into (upsert is idempotent, M7).
        max_queue: the in-memory bound; events enqueued past it are dropped+counted.
    """

    def __init__(self, repository: CostEventRepository, *, max_queue: int = 10_000) -> None:
        if max_queue < 0:
            raise ValueError(f"max_queue must be non-negative, got {max_queue}")
        self._repository = repository
        self._max_queue = max_queue
        self._queue: deque[CostEvent] = deque()
        self._dropped = 0

    @property
    def queued(self) -> int:
        """The number of events currently buffered (not yet drained)."""
        return len(self._queue)

    @property
    def dropped(self) -> int:
        """The cumulative number of events dropped (queue-full or failed write)."""
        return self._dropped

    @property
    def max_queue(self) -> int:
        """The in-memory queue bound."""
        return self._max_queue

    def enqueue(self, event: CostEvent) -> None:
        """Buffer an event for off-path persistence; drop-and-count if full. Never raises.

        Performs NO synchronous repository write — the host call path only pays
        the cost of an in-memory append.
        """
        if len(self._queue) >= self._max_queue:
            self._dropped += 1
            return
        self._queue.append(event)

    def drain(self) -> int:
        """Drain buffered events to the repository off-path; return how many persisted.

        A repository failure on any event is logged and counted as a drop, never
        raised — draining continues for the remaining events. ``tenant_id`` comes
        from each event (every CostEvent is tenant-scoped by construction, §3.2).
        """
        persisted = 0
        while self._queue:
            event = self._queue.popleft()
            tenant_id: TenantId = event.tenant_id
            try:
                self._repository.upsert(tenant_id, event)
            except Exception:
                self._dropped += 1
                _LOGGER.warning(
                    "valuemaxx capture failed to persist a cost event (dropped); "
                    "ingest may be unavailable",
                    exc_info=True,
                )
            else:
                persisted += 1
        return persisted


__all__ = ["Emitter"]
