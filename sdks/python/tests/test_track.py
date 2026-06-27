"""SDK — ``track.run`` sets and resets the ambient run_id (§5.1, H2).

The capture transport patch reads ``active_run_id`` off the contextvar; ``track.run``
is the one-liner the host uses to establish a run, so every LLM call inside the
``with`` block binds to it, and the prior value is restored on exit.
"""

from __future__ import annotations

import pytest
from valuemaxx.core.context import active_run_id
from valuemaxx.core.ids import RunId
from valuemaxx.sdk import track


def test_track_run_sets_active_run_id() -> None:
    """test_track_run_sets_active_run_id: inside the block the contextvar is the run id."""
    assert active_run_id.get() is None
    with track.run(run_id="run-abc"):
        assert active_run_id.get() == RunId("run-abc")
    # restored on exit
    assert active_run_id.get() is None


def test_track_run_restores_prior_run_id() -> None:
    """test_track_run_restores_prior_run_id: nesting restores the outer run id."""
    with track.run(run_id="outer"):
        assert active_run_id.get() == RunId("outer")
        with track.run(run_id="inner"):
            assert active_run_id.get() == RunId("inner")
        assert active_run_id.get() == RunId("outer")


def _raise_in_run() -> None:
    with track.run(run_id="run-x"):
        raise ValueError("host error")


def test_track_run_resets_even_on_exception() -> None:
    """test_track_run_resets_even_on_exception: the contextvar is restored if the body raises."""
    with pytest.raises(ValueError, match="host error"):
        _raise_in_run()
    assert active_run_id.get() is None
