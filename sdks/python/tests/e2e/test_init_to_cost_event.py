"""SDK e2e — init() instruments an injected client; a call produces a CostEvent.

The full producer path through the SDK façade: ``init()`` with an injected client
+ a recording sink instruments the client's transport (instance-scoped, H1);
inside ``track.run`` a transport send produces exactly one CostEvent bound to the
run. The headline H1 guarantee is re-proven here: an UNRELATED ``httpx.Client`` in
the same process is untouched.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import httpx
from typing_extensions import override
from valuemaxx.capture import AttemptObservation
from valuemaxx.core.ids import RunId, TenantId
from valuemaxx.core.repositories import CostEventRepository
from valuemaxx.core.tokens import TokenVector
from valuemaxx.sdk import init, track

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from valuemaxx.core.cost import CostEvent


class _RecordingSink(CostEventRepository):
    def __init__(self) -> None:
        self.events: list[CostEvent] = []

    @override
    def upsert(self, tenant_id: TenantId, event: CostEvent) -> None:
        self.events.append(event)

    @override
    def list_for_run(self, tenant_id: TenantId, run_id: RunId) -> Sequence[CostEvent]:
        return tuple(e for e in self.events if e.run_id == run_id)

    @override
    def list_in_window(
        self, tenant_id: TenantId, start: datetime, end: datetime
    ) -> Sequence[CostEvent]:
        return tuple(self.events)


class _Transport:
    def __init__(self) -> None:
        self.calls = 0

    def send(self, _request: object) -> str:
        self.calls += 1
        return "ok"


class _Client:
    def __init__(self) -> None:
        self._client = _Transport()

    @property
    def transport(self) -> _Transport:
        """The injected transport (== ``_client``); a public accessor for the tests."""
        return self._client


def _usage(_response: object) -> AttemptObservation:
    return AttemptObservation(
        provider="anthropic",
        model="claude-opus-4-8",
        tokens=TokenVector(
            input_uncached=10,
            cache_read=0,
            cache_write_5m=0,
            cache_write_1h=0,
            output=5,
            reasoning=0,
        ),
        is_streaming=False,
    )


def test_init_to_cost_event() -> None:
    """test_init_to_cost_event: init() -> a transport call -> one CostEvent bound to the run."""
    sink = _RecordingSink()
    client = _Client()
    result = init(
        tenant_id=TenantId(uuid4()),
        ingest_key="k",
        endpoint="https://ingest.example",
        client=client,
        sink=sink,
        usage_extractor=_usage,
    )
    assert result.capture_patched is True
    handle = result.instrument_handle
    assert handle is not None

    with track.run(run_id="run-e2e"):
        client.transport.send(object())
    handle.handle_drain()

    assert len(sink.events) == 1
    assert sink.events[0].run_id == RunId("run-e2e")
    handle.uninstrument()


def test_unrelated_httpx_client_is_untouched() -> None:
    """test_unrelated_httpx_client_is_untouched: H1 — only the injected instance is patched."""
    sink = _RecordingSink()
    client = _Client()
    result = init(
        tenant_id=TenantId(uuid4()),
        ingest_key="k",
        endpoint="https://ingest.example",
        client=client,
        sink=sink,
        usage_extractor=_usage,
    )

    # an UNRELATED real httpx.Client in the same process
    other = httpx.Client()
    assert "send" not in vars(other)  # its send is the pristine class method
    assert httpx.Client.send is httpx.Client.__dict__["send"]  # class never patched

    assert result.instrument_handle is not None
    result.instrument_handle.uninstrument()
