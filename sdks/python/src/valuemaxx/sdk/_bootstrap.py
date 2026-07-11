"""``init()`` — the one-line, fail-open SDK entrypoint (§5.1, H9).

``init()`` is a thin façade: all real instrumentation lives in ``valuemaxx.capture``.
Only the pydantic validation of the literal config args may raise (a programming
error at the call site); every instrumentation step runs inside a fail-open guard,
so an internal error is logged + surfaced as a warning and NEVER propagates into the
host. It returns an :class:`InitResult` describing what took effect.

Content (prompt/response) is OFF by default (§9.1); the ingest key is a SecretStr
that never reaches a log. The version self-test warns loudly and degrades capture
granularity to ``per_call`` on an incompatible SDK version, never silently capturing
the wrong granularity.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from pydantic import SecretStr
from valuemaxx.capture import Emitter, version_selftest
from valuemaxx.capture.patch import instrument_client
from valuemaxx.outcomes.instrument.baggage import install_run_id_baggage
from valuemaxx.outcomes.instrument.injection import install_run_id_injection
from valuemaxx.sdk.config import EffectiveConfig, InitConfig

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from valuemaxx.capture import AttemptObservation, InstrumentHandle
    from valuemaxx.core.context import Clock, UuidGen
    from valuemaxx.core.ids import TenantId
    from valuemaxx.core.pricing import PriceBook
    from valuemaxx.core.repositories import CostEventRepository
    from valuemaxx.outcomes.instrument.injection import InjectionReport
    from valuemaxx.outcomes.schema import RunIdInjectionSpec

_LOGGER = logging.getLogger("valuemaxx.sdk.init")


@dataclass(frozen=True, slots=True)
class InitResult:
    """The outcome of :func:`init`: what was patched, the effective config, warnings."""

    capture_patched: bool
    capture_granularity: str
    warnings: tuple[str, ...]
    effective: EffectiveConfig
    instrument_handle: InstrumentHandle | None = field(default=None)


class _RealClock:
    """The production clock (injectable elsewhere so tests stay deterministic)."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class _CountingUuid:
    """The production uuid generator (injectable elsewhere for reproducible tests)."""

    def new(self) -> str:
        return uuid4().hex


def _unresolved_warnings(report: InjectionReport, *, channel: str) -> list[str]:
    """Turn each unresolved carry target into a named startup warning (H10, never silent)."""
    return [
        f"valuemaxx: {channel} not importable at init (run_id will NOT round-trip): {target}"
        for target in report.unresolved
    ]


def init(
    *,
    tenant_id: TenantId,
    ingest_key: str,
    endpoint: str,
    capture_content: bool = False,
    service_name: str = "valuemaxx",
    max_queue_size: int = 10_000,
    installed_versions: Mapping[str, str] | None = None,
    client: object | None = None,
    sink: CostEventRepository | None = None,
    usage_extractor: Callable[[object], AttemptObservation | None] | None = None,
    pricebook: PriceBook | None = None,
    clock: Clock | None = None,
    uuid_gen: UuidGen | None = None,
    run_id_injection_specs: Sequence[RunIdInjectionSpec] | None = None,
    baggage_targets: Sequence[str] | None = None,
) -> InitResult:
    """Instrument cost capture in one call. Never raises into the host (fail-open, H9).

    The config args are validated by pydantic first (a bad literal raises at the
    call site, as intended); every instrumentation step thereafter is fail-open.
    When an injected ``client`` + ``sink`` are provided the client's transport is
    instrumented (instance-scoped, H1) and the returned ``instrument_handle`` lets
    the caller drain/uninstrument; otherwise ``init`` validates + self-tests only.
    """
    # config validation (the ONLY part allowed to raise — a call-site programming error)
    config = InitConfig(
        tenant_id=tenant_id,
        ingest_key=SecretStr(ingest_key),
        endpoint=endpoint,
        capture_content=capture_content,
        service_name=service_name,
        max_queue_size=max_queue_size,
    )
    effective = EffectiveConfig(
        tenant_id=config.tenant_id,
        endpoint=config.endpoint,
        capture_content=config.capture_content,
        service_name=config.service_name,
        max_queue_size=config.max_queue_size,
    )

    warnings: list[str] = []
    granularity = "per_attempt"
    handle: InstrumentHandle | None = None
    patched = False

    # everything below is fail-open: an internal error is logged + warned, never raised.
    try:
        installed: Mapping[str, str] = installed_versions if installed_versions is not None else {}
        selftest = version_selftest(installed_versions=installed, hook_present=client is not None)
        warnings.extend(selftest.warnings)
        granularity = selftest.granularity.value

        if client is not None and sink is not None and usage_extractor is not None:
            from valuemaxx.core.enums import CaptureGranularity

            handle = instrument_client(
                client,
                emitter=Emitter(sink, max_queue=config.max_queue_size),
                tenant_id=config.tenant_id,
                clock=clock or _RealClock(),
                uuid_gen=uuid_gen or _CountingUuid(),
                pricebook=pricebook,
                usage_extractor=usage_extractor,
                granularity=CaptureGranularity(granularity),
            )
            patched = True

        # T3 — auto-wrap the onboarded echoing SDK calls so the run_id round-trips (§6.1).
        if run_id_injection_specs:
            report = install_run_id_injection(run_id_injection_specs)
            warnings.extend(_unresolved_warnings(report, channel="run_id injection sdk_call"))
        # T2 — auto-wrap outbound HTTP so the run_id rides W3C baggage across a live hop.
        if baggage_targets:
            report = install_run_id_baggage(baggage_targets)
            warnings.extend(_unresolved_warnings(report, channel="baggage target"))
    except Exception as exc:
        warnings.append(f"valuemaxx init suppressed an internal error (fail-open): {exc}")
        _LOGGER.warning("valuemaxx init suppressed an internal error (fail-open)", exc_info=True)

    return InitResult(
        capture_patched=patched,
        capture_granularity=granularity,
        warnings=tuple(warnings),
        effective=effective,
        instrument_handle=handle,
    )


__all__ = ["InitResult", "init"]
