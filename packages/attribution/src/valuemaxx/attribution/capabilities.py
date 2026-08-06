"""Capability projection for the attribution package (ATTR-4, M10).

``register(registry)`` projects the binding cascade onto the capability registry as
two request/response capabilities on the API|MCP|CLI surfaces:

- ``bind_outcome`` — bind one :class:`~valuemaxx.core.OutcomeEvent` to its run,
  returning the labeled :class:`~valuemaxx.core.AttributionResult`.
- ``list_review_queue`` — return the pending review :class:`~valuemaxx.core.AttributionResult`
  for the (tenant-scoped) outcome (candidate/likely/unbound items awaiting a human).

Both capabilities' I/O are ``valuemaxx.core`` domain models — no domain type is
defined in this package (the ``no_type_outside_core`` rule). The runtime
dependencies (the :class:`~valuemaxx.attribution.cascade.Cascade` and the
:class:`~valuemaxx.core.ReviewQueue`) are injected by the app at startup via
:func:`bind_runtime`; until then the handlers raise :class:`~valuemaxx.core.AtmError`
rather than silently no-op.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING
from weakref import WeakKeyDictionary

from valuemaxx.attribution.binding.baggage_header import parse_baggage_header
from valuemaxx.attribution.cascade import Cascade
from valuemaxx.capabilities import Mode, Surface, capability
from valuemaxx.core import AtmError, AttributionResult, OutcomeEvent, Run, RunId
from valuemaxx.core.outcome import OutcomeBinding
from valuemaxx.core.wire import BAGGAGE_RUN_ID_KEY

if TYPE_CHECKING:
    from collections.abc import Mapping
    from contextvars import Token
    from datetime import timedelta

    from valuemaxx.capabilities import Registry
    from valuemaxx.core import LlmJudge, OutcomeEventRepository, ReviewQueue, RunRepository

_SURFACES = Surface.API | Surface.MCP | Surface.CLI


class AttributionNotWiredError(AtmError):
    """A capability handler was invoked before its runtime was bound (M10)."""


@dataclass(frozen=True, slots=True)
class AttributionRuntime:
    """The runtime dependencies an app injects to power the attribution capabilities.

    Constructs the cascade from the injected core ABCs/Protocols. The same
    ``review_queue`` instance is exposed so ``list_review_queue`` reads exactly
    what the cascade wrote.
    """

    run_repo: RunRepository
    review_queue: ReviewQueue
    entity_window: timedelta
    judge: LlmJudge | None = None
    semantic_window: timedelta | None = None
    # Optional so the pure cascade stays usable without a store. When supplied,
    # `bind_outcome` PERSISTS the outcome (carrying the tier the cascade just
    # assigned) — without it the binding is computed, returned, and forgotten, so no
    # metric ever counts the outcome and cost-per-outcome divides by zero forever.
    outcome_repo: OutcomeEventRepository | None = None

    def cascade(self) -> Cascade:
        """Build the cascade over this runtime's dependencies."""
        return Cascade(
            run_repo=self.run_repo,
            review_queue=self.review_queue,
            judge=self.judge,
            entity_window=self.entity_window,
            semantic_window=self.semantic_window,
        )


class _RuntimeHolder:
    """A late-bound slot for one registry's attribution runtime."""

    __slots__ = ("runtime",)

    def __init__(self) -> None:
        self.runtime: AttributionRuntime | None = None

    def require(self) -> AttributionRuntime:
        """Return the bound runtime, or raise if the app never wired it."""
        if self.runtime is None:
            raise AttributionNotWiredError(
                "attribution capabilities are not wired; call "
                "valuemaxx.attribution.bind_runtime(registry, runtime) at app startup"
            )
        return self.runtime


# One holder per registry instance, keyed by identity (a registry is unhashable-safe
# here because we key on ``id``; the holder lifetime matches the registry's).
# Keyed by the registry OBJECT, weakly — never by ``id()``. CPython recycles memory
# addresses, so an id-keyed dict lets a garbage-collected registry leave a stale holder
# behind at the same address: a brand-new registry then looks already-registered, and
# the "not wired" guard silently stops firing. That is an order-dependent flake by
# construction (it depends on allocation, so it reproduces in CI and not locally), and
# it blocked a release. A weak key dies with the registry, so the entry cannot outlive
# the object it describes.
_HOLDERS: WeakKeyDictionary[object, _RuntimeHolder] = WeakKeyDictionary()


def register(registry: Registry) -> None:
    """Project the attribution capabilities onto ``registry`` (push registration).

    Creates a late-bound runtime holder for this registry and registers the two
    capabilities' handlers closing over it. The app calls :func:`bind_runtime` to
    supply the runtime before any handler is invoked.
    """
    holder = _HOLDERS.setdefault(registry, _RuntimeHolder())

    def bind_outcome_handler(outcome: OutcomeEvent) -> AttributionResult:
        # A caller that already knows the run (the SDK's in-process carry, or an
        # integration posting the run id it just used) supplies it on the event's
        # `binding`. Feed that in as the ambient signal: the cascade still REVALIDATES
        # it against the run repository and refuses a dangling id, so this cannot bind
        # a ghost — it only stops us discarding a deterministic signal the caller
        # already has. Without this, `binding.run_id` was read by nothing at all, and
        # every outcome fell through to the advisory tiers no matter what was sent,
        # leaving cost-per-outcome permanently null.
        runtime = holder.require()
        _ensure_run_exists(runtime, outcome)
        # Transport-borne signals the OutcomeEvent body cannot carry: a W3C `baggage`
        # header (T2) and an echoed run id from an external system (T3). Both are set
        # by the surface via `attribution_request_scope`. They were built, tested, and
        # wired to nothing — this handler passed only `ambient_run_id`, so a
        # baggage-carried run id was silently discarded and the outcome fell to the
        # advisory tiers no matter what the caller sent.
        carried = _signals()
        result = runtime.cascade().bind(
            outcome,
            ambient_run_id=outcome.binding.run_id,
            baggage=carried.baggage,
            echoed_run_id=carried.echoed_run_id,
        )
        _persist(runtime, outcome, result)
        return result

    def list_review_queue_handler(outcome: OutcomeEvent) -> AttributionResult:
        return _pending_for(holder.require(), outcome)

    registry.register(
        capability(
            name="bind_outcome",
            input_model=OutcomeEvent,
            output_model=AttributionResult,
            handler=bind_outcome_handler,
            description=(
                "Bind an outcome event to the agent run that produced it via the "
                "binding cascade (exact->deterministic->candidate->likely), returning "
                "the tier-labeled attribution result."
            ),
            surfaces=_SURFACES,
            mode=Mode.REQUEST_RESPONSE,
        )
    )
    registry.register(
        capability(
            name="list_review_queue",
            input_model=OutcomeEvent,
            output_model=AttributionResult,
            handler=list_review_queue_handler,
            description=(
                "Return the pending review attribution result for the given "
                "(tenant-scoped) outcome — a candidate/likely/unbound binding "
                "awaiting human confirmation. Advisory, never billing-grade."
            ),
            surfaces=_SURFACES,
            mode=Mode.REQUEST_RESPONSE,
        )
    )


def bind_runtime(registry: Registry, runtime: AttributionRuntime) -> None:
    """Wire ``runtime`` into the capabilities registered for ``registry``.

    Raises :class:`AttributionNotWiredError` if :func:`register` was never called
    for this registry (there is no holder to bind into).
    """
    holder = _HOLDERS.get(registry)
    if holder is None:
        raise AttributionNotWiredError(
            "no attribution capabilities registered for this registry; call register() first"
        )
    holder.runtime = runtime


@dataclass(frozen=True, slots=True)
class _RequestSignals:
    """Transport-borne attribution signals for one inbound request."""

    baggage: Mapping[str, str] | None = None
    echoed_run_id: RunId | None = None


# `None` rather than a shared `_RequestSignals()` default: a mutable default on a
# ContextVar is one object across every context, so a future mutable field would
# bleed between requests. Readers normalize with `_signals()`.
_REQUEST_SIGNALS: ContextVar[_RequestSignals | None] = ContextVar(
    "valuemaxx_attribution_signals", default=None
)

_NO_SIGNALS = _RequestSignals()


def _signals() -> _RequestSignals:
    """The current request's transport signals, or the empty set."""
    return _REQUEST_SIGNALS.get() or _NO_SIGNALS


class attribution_request_scope:  # noqa: N801 - a context manager, reads like one
    """Supply transport-borne attribution signals for the duration of the block.

    `OutcomeEvent` is the wire body; a `baggage` header and an echoed run id ride the
    transport instead, so they cannot be fields on it without letting a caller forge
    them. The surface parses them from the request and scopes them here.

    A malformed baggage header parses to an empty map rather than raising — an ingest
    path must degrade to the advisory tiers, never 500 on a junk header.
    """

    __slots__ = ("_signals", "_token")

    def __init__(
        self, *, baggage: str | None = None, echoed_run_id: RunId | None = None
    ) -> None:
        parsed = parse_baggage_header(baggage) if baggage else None
        self._signals = _RequestSignals(
            baggage=parsed or None, echoed_run_id=echoed_run_id
        )
        self._token: Token[_RequestSignals | None] | None = None

    def __enter__(self) -> None:
        self._token = _REQUEST_SIGNALS.set(self._signals)

    def __exit__(self, *_exc: object) -> None:
        if self._token is not None:
            _REQUEST_SIGNALS.reset(self._token)
            self._token = None


def _carried_run_id(signals: _RequestSignals) -> RunId | None:
    """The run id a transport signal carried, if any (echo wins over baggage)."""
    if signals.echoed_run_id is not None:
        return signals.echoed_run_id
    if signals.baggage is None:
        return None
    value = signals.baggage.get(BAGGAGE_RUN_ID_KEY)
    return RunId(value) if value else None


def _ensure_run_exists(runtime: AttributionRuntime, outcome: OutcomeEvent) -> None:
    """Register the caller-supplied run on first sight, so binding is order-independent.

    Cost spans are BATCHED and an outcome POSTs immediately, so the ordinary arrival
    order is outcome-first: the run row (written when a cost span is ingested) does
    not exist yet. The cascade revalidates every deterministic run id and refuses one
    it cannot find — correct against a *dangling* id, but here the id is merely
    EARLY, and the two are indistinguishable at the repository. Since nothing ever
    retries a binding, the outcome would stay advisory forever and its cost never
    join, which is the whole failure this closes.

    Registering here is safe because the caller is asserting the run id it just used,
    the same assertion the span path makes when it registers a run. The upsert is
    idempotent, so the later cost span lands on this row and enriches it with the
    agent name and entity keys the span carries. We claim no more than we know:
    `agent_name` stays None (an outcome does not know it) and `started_at` is the
    outcome's own timestamp — the earliest moment we can prove the run existed,
    never a fabricated clock reading.

    A run id we did NOT get from the caller is not invented: no run id means the
    cascade falls through to the advisory tiers exactly as before.
    """
    # The body's run id, or the one the transport carried (baggage/echo). Both are
    # caller assertions of a run that exists, and both hit the same ordering hazard:
    # cost spans are batched, so the run row may not be written yet and the cascade
    # would refuse the id as dangling. Registering on first sight makes binding
    # independent of which arrives first.
    carried = _signals()
    run_id = outcome.binding.run_id or _carried_run_id(carried)
    if run_id is None:
        return
    repo = runtime.run_repo
    if repo.get(outcome.tenant_id, run_id) is not None:
        return
    repo.upsert(
        outcome.tenant_id,
        Run(
            tenant_id=outcome.tenant_id,
            id=run_id,
            agent_name=None,
            started_at=outcome.occurred_at,
            ended_at=None,
            entity_keys=outcome.entity_keys,
        ),
    )


def _persist(runtime: AttributionRuntime, outcome: OutcomeEvent, result: AttributionResult) -> None:
    """Store the outcome with the binding the cascade just assigned.

    The cascade is a pure function over repositories — it decides a tier but writes no
    outcome. Something has to persist it or the outcome exists only in the HTTP
    response: metrics load outcomes from the store, so an unpersisted outcome makes
    `verified_outcome_count` zero and `cost_per_outcome` null no matter how cleanly it
    bound. We write the RESULT's binding, not the caller's, so the stored tier is the
    system-owned one (a caller cannot promote its own outcome to `exact`).
    """
    repo = runtime.outcome_repo
    if repo is None:
        return
    repo.upsert(
        outcome.tenant_id,
        outcome.model_copy(
            update={
                "binding": OutcomeBinding(
                    run_id=result.run_id, tier=result.tier, bound_by=result.bound_by
                )
            }
        ),
    )


def _pending_for(runtime: AttributionRuntime, outcome: OutcomeEvent) -> AttributionResult:
    """The pending review result for ``outcome`` within its tenant scope.

    Foundation-constrained projection: the capability output is a single core
    :class:`~valuemaxx.core.AttributionResult` (no list-wrapping model may be
    defined outside core), so this returns the pending item for this outcome's id,
    raising if there is none.
    """
    for item in runtime.review_queue.list_pending(outcome.tenant_id):
        if isinstance(item, AttributionResult) and item.outcome_id == outcome.id:
            return item
    raise AttributionNotWiredError(
        f"no pending review item for outcome {outcome.id!r} in tenant scope"
    )


__all__ = [
    "AttributionNotWiredError",
    "AttributionRuntime",
    "attribution_request_scope",
    "bind_runtime",
    "register",
]
