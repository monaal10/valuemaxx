"""LIVE-TEST RATCHET — ingest real Vercel AI SDK (v6) span attributes.

Caught on live vibechk (AI SDK ``ai@6.0.168``): the SDK's ``experimental_telemetry``
emits token usage under **``ai.usage.*``** keys on the ``ai.generateText.doGenerate``
span — NOT the ``gen_ai.usage.input_tokens`` / ``gen_ai.usage.output_tokens`` keys
the collector decoded. The provider (``gen_ai.system``) and model
(``gen_ai.request.model``) keys DO match. So a real Vercel-AI-SDK span reached
``/v1/traces`` but mapped to **0 tokens** -> wrong/zero cost (a silent mis-capture).

Fix: ``span_to_cost_event`` reads the AI-SDK ``ai.usage.*`` keys as a fallback when
the canonical ``gen_ai.usage.*`` keys are absent. These vendor keys are an ingest-side
ADAPTER (see ``vendor_aliases``) — deliberately NOT added to the cross-language
``ALL_KEYS`` contract (valuemaxx does not *emit* them). v6 semantics
(``inputTokenDetails``): ``ai.usage.inputTokens`` is the TOTAL input (cached + uncached),
exactly the ``total_input`` ``TokenVector.from_provider`` expects, with cache read/write
as subsets — so the cache invariant holds.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from valuemaxx.capture.otlp.otlp_ingest import span_to_cost_event
from valuemaxx.core.enums import TokenClass
from valuemaxx.core.ids import TenantId
from valuemaxx.core.pricing import PriceBook, PriceCard

_TENANT = TenantId(uuid4())
_AT = datetime(2026, 6, 27, tzinfo=UTC)


class _FixedClock:
    def now(self) -> datetime:
        return _AT


def _pricebook() -> PriceBook:
    return PriceBook(
        cards=(
            PriceCard(
                provider="anthropic",
                model="claude-3-5-haiku",
                usd_per_mtok={
                    TokenClass.INPUT_UNCACHED: Decimal("0.80"),
                    TokenClass.CACHE_READ: Decimal("0.08"),
                    TokenClass.OUTPUT: Decimal("4.00"),
                },
                effective_from=_AT,
                rule_version="v1",
            ),
        )
    )


def test_vercel_ai_sdk_usage_keys_map_to_tokens() -> None:
    """A span with ONLY ai.usage.* keys (the real v6 shape) yields the right tokens + cost."""
    # The exact attribute shape AI SDK v6 sets on ai.generateText.doGenerate.
    attrs: dict[str, object] = {
        "gen_ai.system": "anthropic",
        "gen_ai.request.model": "claude-3-5-haiku",
        "ai.usage.inputTokens": 1000,  # TOTAL input (incl. cached) — v6 semantics
        "ai.usage.outputTokens": 250,
        "ai.usage.inputTokenDetails.cacheReadTokens": 200,
        "ai.usage.outputTokenDetails.reasoningTokens": 50,
        "ai_margin.run_id": "vibechk-run",
        "ai_margin.attempt_id": "att-1",
    }
    event = span_to_cost_event(
        attrs, tenant_id=_TENANT, pricebook=_pricebook(), clock=_FixedClock()
    )

    assert event.provider == "anthropic"
    assert event.model == "claude-3-5-haiku"
    # total input 1000 = 200 cache_read + 800 uncached; output 250 incl 50 reasoning.
    assert event.tokens.total_input == 1000
    assert event.tokens.cache_read == 200
    assert event.tokens.input_uncached == 800
    assert event.tokens.output == 250
    assert event.tokens.reasoning == 50
    # a real cost was computed (not zero), so the capture is not a silent mis-map.
    assert event.cost_usd is not None
    assert event.cost_usd > Decimal("0")


def test_canonical_gen_ai_keys_still_win_when_present() -> None:
    """If canonical gen_ai.usage.* keys are present, they take precedence over ai.usage.*."""
    attrs: dict[str, object] = {
        "gen_ai.system": "anthropic",
        "gen_ai.request.model": "claude-3-5-haiku",
        "gen_ai.usage.input_tokens": 500,  # canonical — must win
        "gen_ai.usage.output_tokens": 100,
        "ai.usage.inputTokens": 9999,  # vendor alias — ignored when canonical present
        "ai.usage.outputTokens": 8888,
    }
    event = span_to_cost_event(
        attrs, tenant_id=_TENANT, pricebook=_pricebook(), clock=_FixedClock()
    )
    assert event.tokens.total_input == 500
    assert event.tokens.output == 100


def test_langchain_openllmetry_prompt_completion_keys_map() -> None:
    """LangChain/OpenLLMetry spans (gen_ai.usage.prompt_tokens/completion_tokens) map."""
    attrs: dict[str, object] = {
        "gen_ai.system": "anthropic",  # matches the test pricebook card
        "gen_ai.request.model": "claude-3-5-haiku",
        "gen_ai.usage.prompt_tokens": 800,  # the OLDER GenAI spelling LangChain emits
        "gen_ai.usage.completion_tokens": 200,
    }
    event = span_to_cost_event(
        attrs, tenant_id=_TENANT, pricebook=_pricebook(), clock=_FixedClock()
    )
    assert event.tokens.total_input == 800
    assert event.tokens.output == 200
    assert event.cost_usd is not None
    assert event.cost_usd > Decimal("0")


def test_openinference_llm_token_count_keys_map_with_provider_and_model() -> None:
    """OpenInference spans (llm.token_count.*, llm.system, llm.model_name) map fully."""
    attrs: dict[str, object] = {
        # OpenInference names provider+model differently — aliased to canonical here.
        "llm.system": "anthropic",
        "llm.model_name": "claude-3-5-haiku",
        "llm.token_count.prompt": 600,
        "llm.token_count.completion": 150,
    }
    event = span_to_cost_event(
        attrs, tenant_id=_TENANT, pricebook=_pricebook(), clock=_FixedClock()
    )
    assert event.provider == "anthropic"
    assert event.model == "claude-3-5-haiku"
    assert event.tokens.total_input == 600
    assert event.tokens.output == 150
    assert event.cost_usd is not None
    assert event.cost_usd > Decimal("0")


def test_unknown_model_is_captured_but_unpriced_not_crashed_or_faked() -> None:
    """A Gemini/unknown model with no price card is captured honestly: cost None, not /bin/zsh."""
    attrs: dict[str, object] = {
        "gen_ai.system": "google",
        "gen_ai.request.model": "gemini-2.5-flash",  # not in the test pricebook
        "ai.usage.inputTokens": 1000,
        "ai.usage.outputTokens": 250,
    }
    event = span_to_cost_event(
        attrs, tenant_id=_TENANT, pricebook=_pricebook(), clock=_FixedClock()
    )
    # tokens still captured (provider/model recorded), but cost is honestly None.
    assert event.tokens.total_input == 1000
    assert event.tokens.output == 250
    assert event.cost_usd is None
    assert event.billing_uncertain_abort is True
