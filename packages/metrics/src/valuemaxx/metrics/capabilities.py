"""Capability projection for the metrics package (M10).

``register(registry)`` projects the metric engine onto the capability registry as
one request/response capability on the API|MCP|CLI surfaces:

- ``run_metric`` — validate + compile + run a user-defined
  :class:`~valuemaxx.core.MetricDefinition`, returning a
  :class:`~valuemaxx.metrics.schemas.MetricResult` carrying both H7 fields per cell
  and the H8 re-emit signal.

The capability input is the core ``MetricDefinition`` domain model; the output is
the package's response envelope (``schemas.py``/``capabilities.py`` are on the
``no_type_outside_core`` config-AST allowlist — they shape one capability's
response, they do not redefine a domain type). The runtime (the executor, the
window, the candidate outcomes) is injected by the app at startup via
:func:`bind_runtime`; until then the handler raises rather than silently no-op.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from weakref import WeakKeyDictionary

from valuemaxx.capabilities import Mode, Surface, capability
from valuemaxx.core import AtmError, MetricDefinition
from valuemaxx.metrics.compiler import compile_plan
from valuemaxx.metrics.schemas import MetricResult

if TYPE_CHECKING:
    from collections.abc import Sequence

    from valuemaxx.capabilities import Registry
    from valuemaxx.core import OutcomeEvent, TenantId
    from valuemaxx.metrics.executor import MetricExecutor, MetricWindow

_SURFACES = Surface.API | Surface.MCP | Surface.CLI


class MetricsNotWiredError(AtmError):
    """A capability handler was invoked before its runtime was bound (M10)."""


@dataclass(frozen=True, slots=True)
class MetricRuntime:
    """The runtime dependencies an app injects to power the ``run_metric`` capability.

    Carries the tenant scope, the :class:`~valuemaxx.metrics.executor.MetricExecutor`
    (constructed over the injected core repo ABCs), the metric
    :class:`~valuemaxx.metrics.executor.MetricWindow`, and the candidate outcomes
    the executor applies the H8 denominator rules to.
    """

    tenant_id: TenantId
    executor: MetricExecutor
    window: MetricWindow
    outcomes: Sequence[OutcomeEvent]


class _RuntimeHolder:
    """A late-bound slot for one registry's metric runtime."""

    __slots__ = ("runtime",)

    def __init__(self) -> None:
        self.runtime: MetricRuntime | None = None

    def require(self) -> MetricRuntime:
        """Return the bound runtime, or raise if the app never wired it."""
        if self.runtime is None:
            raise MetricsNotWiredError(
                "metrics capabilities are not wired; call "
                "valuemaxx.metrics.bind_runtime(registry, runtime) at app startup"
            )
        return self.runtime


# One holder per registry instance, keyed by the registry object itself via a weak
# map: when a registry is garbage-collected its holder is dropped, so a later
# registry can never inherit a stale holder through object-id reuse (a hazard a
# plain ``dict[int, ...]`` keyed on ``id(registry)`` would have).
_HOLDERS: WeakKeyDictionary[Registry, _RuntimeHolder] = WeakKeyDictionary()


def register(registry: Registry) -> None:
    """Project the ``run_metric`` capability onto ``registry`` (push registration).

    Creates a late-bound runtime holder for this registry and registers the
    capability handler closing over it. The app calls :func:`bind_runtime` to
    supply the runtime before any handler is invoked.
    """
    holder = _HOLDERS.setdefault(registry, _RuntimeHolder())

    def run_metric_handler(definition: MetricDefinition) -> MetricResult:
        runtime = holder.require()
        plan = compile_plan(definition)
        return runtime.executor.run(
            runtime.tenant_id, plan, runtime.window, runtime.outcomes
        )

    registry.register(
        capability(
            name="run_metric",
            input_model=MetricDefinition,
            output_model=MetricResult,
            handler=run_metric_handler,
            description=(
                "Validate, compile, and run a user-defined metric (a typed "
                "allowlist DSL: filter -> outcome -> join -> measure), returning a "
                "result whose every cell carries the conservative confidence "
                "(minimum_tier + distribution) and excludes candidate/likely and "
                "retracted outcomes from the billing-grade denominator."
            ),
            surfaces=_SURFACES,
            mode=Mode.REQUEST_RESPONSE,
        )
    )


def bind_runtime(registry: Registry, runtime: MetricRuntime) -> None:
    """Wire ``runtime`` into the capability registered for ``registry``.

    Raises :class:`MetricsNotWiredError` if :func:`register` was never called for
    this registry (there is no holder to bind into).
    """
    holder = _HOLDERS.get(registry)
    if holder is None:
        raise MetricsNotWiredError(
            "no metrics capabilities registered for this registry; call register() first"
        )
    holder.runtime = runtime


__all__ = [
    "MetricRuntime",
    "MetricsNotWiredError",
    "bind_runtime",
    "register",
]
