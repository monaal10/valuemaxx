"""valuemaxx.capture — fail-open cost capture for AI Margin Intelligence (§5).

The capture logic package: it instruments the INJECTED provider client's transport
(instance-scoped, H1), prices each token class (Decimal, never float), captures
streaming usage by TERMINAL value (never delta-sum), maps the OTLP wire via the
single-source ``semconv``, and exposes gateway / provider-cost-API sources. Every
path is fail-open — instrumentation NEVER throws into the host call (H9).

Depends only on ``valuemaxx.core`` (ABCs/Protocols + domain types) and
``valuemaxx.capabilities``. Ends with ``register(registry)`` (M10).
"""

from __future__ import annotations

from valuemaxx.capture.capabilities import (
    IngestNotWiredError,
    IngestRuntime,
    bind_ingest_runtime,
    register,
)
from valuemaxx.capture.context_patch import (
    ContextPatchHandle,
    install_threadpool_context_propagation,
    run_id_for_child,
)
from valuemaxx.capture.emit import Emitter
from valuemaxx.capture.gateway import OpenRouterSource
from valuemaxx.capture.guard import DropCounter, guard
from valuemaxx.capture.invariants import (
    PROVISIONED_THROUGHPUT_REASON,
    check_invariants,
    price_or_abort,
)
from valuemaxx.capture.patch import (
    AttemptObservation,
    InstrumentHandle,
    instrument_client,
)
from valuemaxx.capture.pricing import compute_cost_usd
from valuemaxx.capture.provider_costapi import is_marker_source, ptu_cost_event
from valuemaxx.capture.selftest import (
    KNOWN_GOOD,
    SelfTestResult,
    SupportedRange,
    version_selftest,
)
from valuemaxx.capture.terminal import (
    AnthropicStreamAccumulator,
    OpenAIStreamAccumulator,
)

__all__ = [
    "KNOWN_GOOD",
    "PROVISIONED_THROUGHPUT_REASON",
    "AnthropicStreamAccumulator",
    "AttemptObservation",
    "ContextPatchHandle",
    "DropCounter",
    "Emitter",
    "IngestNotWiredError",
    "IngestRuntime",
    "InstrumentHandle",
    "OpenAIStreamAccumulator",
    "OpenRouterSource",
    "SelfTestResult",
    "SupportedRange",
    "bind_ingest_runtime",
    "check_invariants",
    "compute_cost_usd",
    "guard",
    "install_threadpool_context_propagation",
    "instrument_client",
    "is_marker_source",
    "price_or_abort",
    "ptu_cost_event",
    "register",
    "run_id_for_child",
    "version_selftest",
]
