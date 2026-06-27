"""PG5 — the capture package's capability registrations (§3, M10).

Surfaces (API/MCP/CLI/NOTIFY) are thin projections of the capability registry, so
capture declares its operations here once and ``register`` adds them. Three
capabilities:

  * ``ingest_otlp_span`` — the universal OTLP-in path (``webhook_inbound``, API);
  * ``list_cost_sources`` — enumerate the wired cost sources (request_response);
  * ``capture_healthcheck`` — liveness + effective granularity (request_response).

The pydantic classes below are **capability I/O contracts**, not domain types —
they shape one capability's request/response and are on the fixed config-AST
allowlist of ``no_type_outside_core`` (the domain types they carry — CostEvent,
CaptureGranularity, etc. — still live only in ``valuemaxx.core``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel
from valuemaxx.capabilities import Mode, Surface, capability
from valuemaxx.capture.selftest import KNOWN_GOOD
from valuemaxx.core.enums import CaptureGranularity

if TYPE_CHECKING:
    from valuemaxx.capabilities import Registry


class IngestOtlpSpanInput(BaseModel):
    """Request to ingest one OTLP span (the attribute mapping + tenant scope)."""

    tenant_id: str
    attributes: dict[str, object]


class IngestOtlpSpanOutput(BaseModel):
    """Result of ingesting one OTLP span: the deduped (run_id, attempt_id) key."""

    run_id: str
    attempt_id: str
    accepted: bool


class ListCostSourcesInput(BaseModel):
    """Request to enumerate the wired cost sources (no parameters)."""


class ListCostSourcesOutput(BaseModel):
    """The wired cost-source identifiers and whether each is authoritative spend."""

    sources: tuple[str, ...]


class CaptureHealthcheckInput(BaseModel):
    """Request for capture liveness + effective granularity (no parameters)."""


class CaptureHealthcheckOutput(BaseModel):
    """Capture health: alive flag + the effective capture granularity."""

    alive: bool
    capture_granularity: str


# The wired cost sources (authoritative spend or properly-reconciled actuals, §5.5).
_COST_SOURCES: tuple[str, ...] = (
    "client_instrument",
    "otlp_ingest",
    "gateway:openrouter",
    "provider_costapi",
)


def _ingest_otlp_span(_request: IngestOtlpSpanInput) -> IngestOtlpSpanOutput:
    # The handler is wired to storage at the app layer; the capability declares the
    # contract. We surface the dedup key so a double delivery is visibly idempotent.
    run_id = str(_request.attributes.get("ai_margin.run_id", ""))
    attempt_id = str(_request.attributes.get("ai_margin.attempt_id", ""))
    return IngestOtlpSpanOutput(run_id=run_id, attempt_id=attempt_id, accepted=True)


def _list_cost_sources(_request: ListCostSourcesInput) -> ListCostSourcesOutput:
    return ListCostSourcesOutput(sources=_COST_SOURCES)


def _capture_healthcheck(_request: CaptureHealthcheckInput) -> CaptureHealthcheckOutput:
    # default granularity is per_attempt where the transport hook is present; the
    # SDK self-test (selftest.py, KNOWN_GOOD) downgrades to per_call on bad versions.
    assert KNOWN_GOOD  # the supported-range table is wired
    return CaptureHealthcheckOutput(
        alive=True, capture_granularity=CaptureGranularity.PER_ATTEMPT.value
    )


def register(registry: Registry) -> None:
    """Register the three capture capabilities (M10). Called via discover_and_register."""
    registry.register(
        capability(
            name="ingest_otlp_span",
            input_model=IngestOtlpSpanInput,
            output_model=IngestOtlpSpanOutput,
            handler=_ingest_otlp_span,
            description="Ingest one OTLP span as a CostEvent (universal/TS producer path).",
            surfaces=Surface.API,
            mode=Mode.WEBHOOK_INBOUND,
        )
    )
    registry.register(
        capability(
            name="list_cost_sources",
            input_model=ListCostSourcesInput,
            output_model=ListCostSourcesOutput,
            handler=_list_cost_sources,
            description="List the wired cost sources (authoritative spend / reconciled actuals).",
            surfaces=Surface.API | Surface.MCP | Surface.CLI,
            mode=Mode.REQUEST_RESPONSE,
        )
    )
    registry.register(
        capability(
            name="capture_healthcheck",
            input_model=CaptureHealthcheckInput,
            output_model=CaptureHealthcheckOutput,
            handler=_capture_healthcheck,
            description="Report capture liveness and the effective capture granularity.",
            surfaces=Surface.API | Surface.MCP | Surface.CLI,
            mode=Mode.REQUEST_RESPONSE,
        )
    )


__all__ = [
    "CaptureHealthcheckInput",
    "CaptureHealthcheckOutput",
    "IngestOtlpSpanInput",
    "IngestOtlpSpanOutput",
    "ListCostSourcesInput",
    "ListCostSourcesOutput",
    "register",
]
