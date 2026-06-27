"""PG0 — the bounded, non-blocking Emitter: drop-and-count, never raises (§5.1, H9).

The Emitter enqueues CostEvents to a bounded in-memory queue and drains them to a
repository off the host call path. When the queue is full it drops-and-counts;
when the repository fails it logs-and-counts. It NEVER raises into the caller.
"""

from __future__ import annotations

import logging

import pytest
from valuemaxx.capture.emit import Emitter
from valuemaxx.core.ids import CostEventId

from ._fakes import RecordingCostRepo, ThrowingCostRepo, make_cost_event


def test_enqueue_then_drain_persists_via_repo() -> None:
    """test_enqueue_then_drain_persists_via_repo: enqueued events drain to the repo."""
    repo = RecordingCostRepo()
    emitter = Emitter(repo, max_queue=10)
    emitter.enqueue(make_cost_event(1))
    emitter.enqueue(make_cost_event(2))
    drained = emitter.drain()
    assert drained == 2
    assert [e.id for e in repo.upserted] == [CostEventId("ce-1"), CostEventId("ce-2")]


def test_enqueue_is_non_blocking_and_never_writes_synchronously() -> None:
    """test_enqueue_is_non_blocking_and_never_writes_synchronously: enqueue != sync write."""
    repo = RecordingCostRepo()
    emitter = Emitter(repo, max_queue=10)
    emitter.enqueue(make_cost_event(1))
    # enqueue must NOT have touched the repo (write happens off-path on drain)
    assert repo.upserted == []
    assert emitter.queued == 1


def test_full_queue_drops_and_counts() -> None:
    """test_full_queue_drops_and_counts: past the bound, events are dropped AND counted."""
    repo = RecordingCostRepo()
    emitter = Emitter(repo, max_queue=2)
    emitter.enqueue(make_cost_event(1))
    emitter.enqueue(make_cost_event(2))
    emitter.enqueue(make_cost_event(3))  # over the bound
    emitter.enqueue(make_cost_event(4))  # over the bound
    assert emitter.dropped == 2
    assert emitter.queued == 2
    emitter.drain()
    assert [e.id for e in repo.upserted] == [CostEventId("ce-1"), CostEventId("ce-2")]


def test_enqueue_never_raises_even_when_full() -> None:
    """test_enqueue_never_raises_even_when_full: enqueue is fail-open, never throws."""
    repo = RecordingCostRepo()
    emitter = Emitter(repo, max_queue=0)  # nothing fits
    emitter.enqueue(make_cost_event(1))  # must not raise
    assert emitter.dropped == 1
    assert emitter.queued == 0


def test_negative_max_queue_rejected() -> None:
    """test_negative_max_queue_rejected: a negative bound is a programming error, not silent."""
    with pytest.raises(ValueError, match="non-negative"):
        Emitter(RecordingCostRepo(), max_queue=-1)


def test_drain_never_raises_on_repo_failure(caplog: pytest.LogCaptureFixture) -> None:
    """test_drain_never_raises_on_repo_failure: a throwing repo is logged+counted, not raised."""
    repo = ThrowingCostRepo()
    emitter = Emitter(repo, max_queue=10)
    emitter.enqueue(make_cost_event(1))
    with caplog.at_level(logging.WARNING):
        drained = emitter.drain()  # must not raise
    assert drained == 0
    assert emitter.dropped == 1  # the failed write counts as a drop
    assert caplog.records  # the failure was logged, never silent
