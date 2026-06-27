"""PG2 — the H1 INSTANCE-scoped transport patch (§5.1, §5.2). The headline.

We wrap the INJECTED client's own transport — ``client._client.send`` — on the
**instance** via :func:`wrapt.wrap_function_wrapper`. We NEVER patch
``httpx.Client.send`` at the module/class level: an unrelated ``httpx.Client`` in
the same process must be completely untouched (proven by
``test_unrelated_httpx_client_is_untouched``). Per-attempt visibility comes from
the transport layer because retries live in ``_base_client``/``httpx``, *below* the
public ``create()`` (§5.2).

The wrapper:
  1. stamps a fresh ``attempt_id`` (so a retry yields one CostEvent per attempt);
  2. calls the host transport OUTSIDE the fail-open guard, so a host transport
     error propagates untouched (we never swallow the host's exception);
  3. inside the guard, reads ``active_run_id`` off the contextvar, extracts the
     usage object, prices it, and enqueues a per-attempt CostEvent.

:func:`instrument_client` returns a reversible :class:`InstrumentHandle` whose
``uninstrument`` removes the instance-level wrapper and restores the original
transport — capture is always cleanly removable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import wrapt
from valuemaxx.capture.guard import DropCounter, guard
from valuemaxx.capture.invariants import check_invariants, price_or_abort
from valuemaxx.core.context import active_run_id
from valuemaxx.core.cost import CostEvent
from valuemaxx.core.enums import CaptureGranularity, Provenance
from valuemaxx.core.ids import AttemptId, CostEventId, RunId
from valuemaxx.core.provenance import ProvenanceLabel

if TYPE_CHECKING:
    from collections.abc import Callable

    from valuemaxx.capture.emit import Emitter
    from valuemaxx.core.context import Clock, UuidGen
    from valuemaxx.core.ids import TenantId
    from valuemaxx.core.pricing import PriceBook
    from valuemaxx.core.tokens import TokenVector

_LOGGER = logging.getLogger("valuemaxx.capture.patch")

_TRANSPORT_ATTR = "_client"
"""The injected client's own transport lives at ``client._client`` (an httpx.Client)."""

_SEND_METHOD = "send"
"""The transport method we wrap on the INSTANCE — never on the httpx class."""

_UNBOUND_RUN_PREFIX = "unbound:"
"""Prefix for the synthetic run id used when no ambient run_id is set (never None)."""


@dataclass(frozen=True, slots=True)
class AttemptObservation:
    """What an extractor pulls off one transport response: usage + identity.

    Provider-specific response parsing (openai/anthropic, streaming) lives in the
    injected ``usage_extractor`` — the patch itself stays provider-agnostic so it
    can wrap any injected client instance.
    """

    provider: str
    model: str
    tokens: TokenVector
    is_streaming: bool
    billing_uncertain_abort: bool = False
    provisioned_throughput: bool = False
    partial_recovered: bool = False


class InstrumentHandle:
    """A reversible handle over one instrumented client instance.

    ``uninstrument`` removes the instance-level transport wrapper; ``handle_drain``
    flushes the emitter (used by the SDK's background flush and by tests).
    """

    def __init__(self, transport: object, emitter: Emitter, drops: DropCounter) -> None:
        self._transport = transport
        self._emitter = emitter
        self._drops = drops
        self._active = True

    def handle_drain(self) -> int:
        """Drain the emitter to its repository off-path; return how many persisted."""
        return self._emitter.drain()

    @property
    def dropped(self) -> int:
        """The number of telemetry events dropped/suppressed by this handle."""
        return self._drops.count + self._emitter.dropped

    def uninstrument(self) -> None:
        """Remove the instance-level transport wrapper (idempotent). Restores the original."""
        if not self._active:
            return
        # the wrapper was installed as an instance attribute shadowing the class
        # method; deleting it restores the original transport.send.
        if _SEND_METHOD in vars(self._transport):
            delattr(self._transport, _SEND_METHOD)
        self._active = False


def instrument_client(
    client: object,
    *,
    emitter: Emitter,
    tenant_id: TenantId,
    clock: Clock,
    uuid_gen: UuidGen,
    pricebook: PriceBook | None,
    usage_extractor: Callable[[object], AttemptObservation | None],
    granularity: CaptureGranularity = CaptureGranularity.PER_ATTEMPT,
) -> InstrumentHandle:
    """Instrument the INJECTED client's own transport, INSTANCE-scoped (H1).

    Wraps ``client._client.send`` on the instance only. Returns a reversible
    :class:`InstrumentHandle`. Raises :class:`AttributeError` only if the injected
    client has no ``_client`` transport (a programming error at call site, surfaced
    loudly rather than silently capturing nothing).
    """
    transport = getattr(client, _TRANSPORT_ATTR)
    drops = DropCounter()

    def _send_wrapper(
        wrapped: Callable[..., object],
        _instance: object,
        args: tuple[object, ...],
        kwargs: dict[str, object],
    ) -> object:
        # stamp the attempt id BEFORE the call so a retry (a fresh send) gets its own
        attempt_id = AttemptId(uuid_gen.new())
        # (1) HOST TRANSPORT CALL — OUTSIDE the guard: its exception must propagate
        result = wrapped(*args, **kwargs)
        # (2) CAPTURE — inside the fail-open guard: never breaks the host
        with guard(_LOGGER, drop_counter=drops):
            _capture_attempt(
                result,
                attempt_id=attempt_id,
                tenant_id=tenant_id,
                clock=clock,
                uuid_gen=uuid_gen,
                pricebook=pricebook,
                usage_extractor=usage_extractor,
                granularity=granularity,
                emitter=emitter,
            )
        return result

    wrapt.wrap_function_wrapper(transport, _SEND_METHOD, _send_wrapper)
    return InstrumentHandle(transport, emitter, drops)


def _capture_attempt(
    result: object,
    *,
    attempt_id: AttemptId,
    tenant_id: TenantId,
    clock: Clock,
    uuid_gen: UuidGen,
    pricebook: PriceBook | None,
    usage_extractor: Callable[[object], AttemptObservation | None],
    granularity: CaptureGranularity,
    emitter: Emitter,
) -> None:
    """Build and enqueue one per-attempt CostEvent from a transport response."""
    observation = usage_extractor(result)
    if observation is None:
        return  # not a billable LLM response (e.g. a non-completion request)

    run_id = active_run_id.get()
    if run_id is None:
        # a call outside an established run: capture it, labeled, never silently drop
        run_id = RunId(f"{_UNBOUND_RUN_PREFIX}{uuid_gen.new()}")

    card = (
        pricebook.card_for(provider=observation.provider, model=observation.model, at=clock.now())
        if pricebook is not None
        else None
    )
    cost_usd, billing_warnings = price_or_abort(
        observation.tokens,
        card,
        billing_uncertain=observation.billing_uncertain_abort,
        provisioned_throughput=observation.provisioned_throughput,
    )
    shape_warnings = check_invariants(observation.tokens, provider=observation.provider)
    warnings = (*shape_warnings, *billing_warnings)

    event = CostEvent(
        tenant_id=tenant_id,
        id=CostEventId(uuid_gen.new()),
        run_id=run_id,
        attempt_id=attempt_id,
        provider=observation.provider,
        model=observation.model,
        tokens=observation.tokens,
        capture_granularity=granularity,
        provenance=ProvenanceLabel(provenance=Provenance.MEASURED),
        cost_usd=cost_usd,
        is_streaming=observation.is_streaming,
        partial_recovered=observation.partial_recovered,
        billing_uncertain_abort=observation.billing_uncertain_abort
        or observation.provisioned_throughput,
        provenance_warnings=warnings,
        occurred_at=clock.now(),
    )
    emitter.enqueue(event)


__all__ = ["AttemptObservation", "InstrumentHandle", "instrument_client"]
