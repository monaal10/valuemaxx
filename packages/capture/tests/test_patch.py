"""PG2 — the H1 INSTANCE-scoped transport patch (§5.1, §5.2). The headline.

We wrap the INJECTED client's own transport (``client.transport.send``) on the
INSTANCE via ``wrapt.wrap_function_wrapper`` — NEVER ``httpx.Client.send`` at the
module/class level. The proof is ``test_unrelated_httpx_client_is_untouched``: a
second, unrelated ``httpx.Client`` in the same process must emit nothing.

The wrapper stamps an ``attempt_id`` per HTTP attempt (so retries yield one
CostEvent each), reads ``active_run_id`` off the contextvar, and emits fail-open
(the host transport call lives OUTSIDE the guard, so a host transport error is
never swallowed). ``instrument_client`` returns a reversible
:class:`InstrumentHandle` whose ``uninstrument`` restores the original transport.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
from valuemaxx.capture.patch import AttemptObservation, InstrumentHandle, instrument_client
from valuemaxx.core.context import active_run_id
from valuemaxx.core.enums import CaptureGranularity
from valuemaxx.core.ids import RunId
from valuemaxx.core.tokens import TokenVector

from ._fakes import TEST_TENANT, RecordingCostRepo


class _FakeClock:
    def now(self) -> datetime:
        return datetime(2026, 6, 27, tzinfo=UTC)


class _SeqUuid:
    def __init__(self) -> None:
        self._n = 0

    def new(self) -> str:
        self._n += 1
        return f"uuid-{self._n}"


class _FakeTransport:
    """A stand-in for ``client._client`` (the httpx transport) with a ``send`` method."""

    def __init__(self, *, fail_times: int = 0) -> None:
        self.calls = 0
        self._fail_times = fail_times

    def send(self, request: object) -> str:
        self.calls += 1
        if self.calls <= self._fail_times:
            raise httpx.ConnectError("transport boom")
        return f"response-{self.calls}"


class _FakeClient:
    """A stand-in for an injected openai/anthropic client whose transport is _client."""

    def __init__(self, transport: _FakeTransport) -> None:
        self._client = transport

    @property
    def transport(self) -> _FakeTransport:
        """The injected transport (== ``_client``); a public accessor for the tests."""
        return self._client


def _usage_from(_response: object) -> AttemptObservation | None:
    # a deterministic extractor: every response carries the same small usage
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


def _instrument(client: _FakeClient, repo: RecordingCostRepo, **kw: object) -> InstrumentHandle:
    from valuemaxx.capture.emit import Emitter

    return instrument_client(
        client,
        emitter=Emitter(repo, max_queue=100),
        tenant_id=TEST_TENANT,
        clock=_FakeClock(),
        uuid_gen=_SeqUuid(),
        pricebook=None,
        usage_extractor=_usage_from,
        granularity=CaptureGranularity.PER_ATTEMPT,
        **kw,
    )


def test_unrelated_httpx_client_is_untouched() -> None:
    """test_unrelated_httpx_client_is_untouched: H1 — only the injected instance is patched."""
    repo = RecordingCostRepo()
    transport = _FakeTransport()
    client = _FakeClient(transport)
    handle = _instrument(client, repo)

    # an UNRELATED real httpx.Client in the same process
    other = httpx.Client()
    assert "send" not in vars(other)  # its send is the pristine class method
    assert httpx.Client.send is httpx.Client.__dict__["send"]  # class is never patched

    handle.uninstrument()


def test_per_attempt_emit_one_event() -> None:
    """test_per_attempt_emit_one_event: a single transport send emits exactly one CostEvent."""
    repo = RecordingCostRepo()
    transport = _FakeTransport()
    client = _FakeClient(transport)
    handle = _instrument(client, repo)

    token = active_run_id.set(RunId("run-A"))
    try:
        client.transport.send(object())
    finally:
        active_run_id.reset(token)

    handle.handle_drain()
    assert len(repo.upserted) == 1
    assert repo.upserted[0].run_id == RunId("run-A")
    assert repo.upserted[0].capture_granularity is CaptureGranularity.PER_ATTEMPT
    handle.uninstrument()


def test_retry_yields_two_events_one_per_attempt() -> None:
    """test_retry_yields_two_events_one_per_attempt: each HTTP attempt gets its own attempt_id."""
    repo = RecordingCostRepo()
    transport = _FakeTransport()
    client = _FakeClient(transport)
    handle = _instrument(client, repo)

    client.transport.send(object())  # attempt 1
    client.transport.send(object())  # attempt 2 (a retry, at the transport layer)
    handle.handle_drain()

    assert len(repo.upserted) == 2
    attempt_ids = {e.attempt_id for e in repo.upserted}
    assert len(attempt_ids) == 2  # distinct attempt ids
    handle.uninstrument()


def test_patch_does_not_swallow_host_transport_error() -> None:
    """test_patch_does_not_swallow_host_transport_error: host transport error propagates."""
    repo = RecordingCostRepo()
    transport = _FakeTransport(fail_times=1)
    client = _FakeClient(transport)
    handle = _instrument(client, repo)

    with pytest.raises(httpx.ConnectError, match="transport boom"):
        client.transport.send(object())

    handle.handle_drain()
    assert repo.upserted == []  # no event when the host transport itself failed
    handle.uninstrument()


def test_uninstrument_restores_transport() -> None:
    """test_uninstrument_restores_transport: uninstrument removes the instance-level wrapper."""
    repo = RecordingCostRepo()
    transport = _FakeTransport()
    client = _FakeClient(transport)
    handle = _instrument(client, repo)
    assert "send" in vars(transport)  # wrapper installed on the instance

    handle.uninstrument()
    assert "send" not in vars(transport)  # restored to the class method

    # after uninstrument, sending emits nothing
    client.transport.send(object())
    handle.handle_drain()
    assert repo.upserted == []


def test_run_id_read_from_active_contextvar() -> None:
    """test_run_id_read_from_active_contextvar: the emitted event binds the ambient run_id."""
    repo = RecordingCostRepo()
    transport = _FakeTransport()
    client = _FakeClient(transport)
    handle = _instrument(client, repo)

    token = active_run_id.set(RunId("ctx-run"))
    try:
        client.transport.send(object())
    finally:
        active_run_id.reset(token)
    handle.handle_drain()
    assert repo.upserted[0].run_id == RunId("ctx-run")
    handle.uninstrument()


def test_no_run_id_uses_unbound_placeholder() -> None:
    """test_no_run_id_uses_unbound_placeholder: a call outside a run still captures, labeled."""
    repo = RecordingCostRepo()
    transport = _FakeTransport()
    client = _FakeClient(transport)
    handle = _instrument(client, repo)

    # no active_run_id set
    client.transport.send(object())
    handle.handle_drain()
    assert len(repo.upserted) == 1
    # the run_id is a generated unbound id, never None (CostEvent.run_id is required)
    assert repo.upserted[0].run_id
    handle.uninstrument()
