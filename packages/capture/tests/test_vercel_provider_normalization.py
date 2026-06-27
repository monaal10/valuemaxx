"""LIVE-TEST RATCHET — normalize Vercel AI SDK provider strings + skip the rollup span.

Caught running THIS repo's valuemaxx against the real vibechk `ai@6.0.168` (peeked at
the actual exported OTLP spans). Two real gaps the synthetic tests missed:

1. AI SDK v6 sets ``gen_ai.system`` to the ``<vendor>.<api>`` form — ``"anthropic.messages"``,
   ``"openai.chat"``, ``"google.generative-ai"`` — NOT the bare vendor. Pricebooks (and
   humans) key on the bare vendor (``anthropic``), so the dated/suffixed provider missed
   every price card -> cost 0. ``normalize_provider`` strips the API suffix on ingest.

2. v6 emits TWO spans per call: the ``ai.generateText.doGenerate`` ATTEMPT span (carries
   provider + model + usage) and the ``ai.generateText`` ROLLUP span (carries ``ai.usage.*``
   but NO ``gen_ai.system`` and NO model). Ingesting the rollup produced a spurious
   empty-provider, zero-cost CostEvent (and risks double-counting tokens). A span with no
   resolvable provider AND no model is skipped — it is a rollup, not a billable attempt.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import uuid4

from typing_extensions import override
from valuemaxx.capabilities import Registry
from valuemaxx.capture.capabilities import (
    IngestRuntime,
    bind_ingest_runtime,
    ingest_attribute_maps,
    register,
)
from valuemaxx.capture.default_pricing import default_pricebook
from valuemaxx.capture.otlp.otlp_ingest import span_to_cost_event
from valuemaxx.capture.otlp.vendor_aliases import normalize_provider
from valuemaxx.core.ids import TenantId
from valuemaxx.core.repositories import CostEventRepository

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime as _dt

    from valuemaxx.core.cost import CostEvent
    from valuemaxx.core.ids import RunId

_AT = datetime(2026, 6, 27, tzinfo=UTC)


class _Clock:
    def now(self) -> datetime:
        return _AT


def test_normalize_provider_strips_ai_sdk_api_suffix() -> None:
    """The AI SDK <vendor>.<api> provider string normalizes to the bare vendor."""
    assert normalize_provider("anthropic.messages") == "anthropic"
    assert normalize_provider("openai.chat") == "openai"
    assert normalize_provider("openai.responses") == "openai"
    assert normalize_provider("google.generative-ai") == "google"
    # a bare vendor (valuemaxx's own SDK, or a gateway) is unchanged
    assert normalize_provider("anthropic") == "anthropic"
    assert normalize_provider("openrouter") == "openrouter"


def test_vercel_suffixed_provider_prices_against_default_book() -> None:
    """A real v6 span (gen_ai.system='anthropic.messages') prices from the default book."""
    attrs: dict[str, object] = {
        "gen_ai.system": "anthropic.messages",  # the real v6 value
        "gen_ai.request.model": "claude-3-5-haiku",
        "gen_ai.usage.input_tokens": 1_000_000,
        "gen_ai.usage.output_tokens": 1_000_000,
    }
    event = span_to_cost_event(
        attrs, tenant_id=TenantId(uuid4()), pricebook=default_pricebook(), clock=_Clock()
    )
    assert event.provider == "anthropic"  # normalized, so it priced
    # claude-3-5-haiku: 1M in @0.80 + 1M out @4.00 = 4.80
    assert event.cost_usd == Decimal("4.800000")


def test_rollup_span_without_provider_or_model_is_skipped() -> None:
    """The AI SDK ai.generateText ROLLUP span (no provider, no model) is not persisted.

    v6 exports both the doGenerate attempt span (provider+model+usage) and a parent
    ai.generateText rollup (ai.usage.* but no gen_ai.system / model). Ingesting the rollup
    would create a spurious empty-provider zero-cost event and risk double-counting. The
    collector persists only spans that resolve a provider or a model.
    """
    captured: list[CostEvent] = []

    class _Repo(CostEventRepository):
        @override
        def upsert(self, tenant_id: TenantId, event: CostEvent) -> None:
            captured.append(event)

        @override
        def list_for_run(self, tenant_id: TenantId, run_id: RunId) -> Sequence[CostEvent]:
            return ()

        @override
        def list_in_window(
            self, tenant_id: TenantId, start: _dt, end: _dt
        ) -> Sequence[CostEvent]:
            return ()

    registry = Registry()
    register(registry)
    bind_ingest_runtime(
        registry, IngestRuntime(repo=_Repo(), pricebook=default_pricebook(), clock=_Clock())
    )

    attempt: dict[str, object] = {  # doGenerate: real provider + model + usage -> persisted
        "gen_ai.system": "anthropic.messages",
        "gen_ai.request.model": "claude-3-5-haiku",
        "gen_ai.usage.input_tokens": 1000,
        "gen_ai.usage.output_tokens": 250,
    }
    rollup: dict[str, object] = {  # ai.generateText: ai.* + model but NO gen_ai.system -> skip
        "ai.model.id": "claude-3-5-haiku",  # the rollup DOES carry this (real v6 shape)
        "ai.usage.inputTokens": 1000,
        "ai.usage.outputTokens": 250,
    }
    persisted = ingest_attribute_maps(registry, TenantId(uuid4()), [attempt, rollup])
    assert persisted == 1, "only the attempt span should persist; the rollup is skipped"
    assert captured[0].provider == "anthropic"
