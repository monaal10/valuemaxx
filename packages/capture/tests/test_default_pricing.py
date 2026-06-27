"""Starter default pricebook — real costs out of the box for OpenAI/Anthropic/Gemini.

valuemaxx shipped 0 price cards, so every OTLP-ingested span was unpriced unless the
caller supplied a pricebook or an inline gateway cost. This adds a curated snapshot
(public list prices as of mid-2026) covering the current OpenAI, Anthropic, and Google
Gemini families, with a family-prefix resolver so a dated model id
(``claude-3-5-haiku-20241022``) matches its family card. Prices are a *snapshot* a user
can override; they are NOT authoritative billing — provenance stays ``estimated``.

These tests pin: known families price (non-zero), the provider-specific token classes
are present (Anthropic cache-writes; OpenAI/Gemini cache-read), a dated/suffixed id
resolves to its family, and a genuinely unknown model stays honestly unpriced.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from valuemaxx.capture.default_pricing import default_pricebook, resolve_card
from valuemaxx.core.enums import TokenClass

_AT = datetime(2026, 6, 27, tzinfo=UTC)


def test_default_pricebook_covers_the_three_provider_families() -> None:
    """At least one card exists for openai, anthropic, and google."""
    providers = {card.provider for card in default_pricebook().cards}
    assert {"openai", "anthropic", "google"} <= providers


def test_known_models_price_nonzero_for_each_provider() -> None:
    """A representative model from each provider resolves to a card with input+output rates."""
    book = default_pricebook()
    cases = [
        ("anthropic", "claude-3-5-haiku"),
        ("openai", "gpt-4.1"),
        ("google", "gemini-2.5-flash"),
    ]
    for provider, model in cases:
        card = resolve_card(book, provider=provider, model=model, at=_AT)
        assert card is not None, f"{provider}/{model} should be priced by default"
        assert card.usd_per_mtok.get(TokenClass.INPUT_UNCACHED, Decimal("0")) > Decimal("0")
        assert card.usd_per_mtok.get(TokenClass.OUTPUT, Decimal("0")) > Decimal("0")


def test_anthropic_card_has_distinct_cache_write_classes() -> None:
    """Anthropic prices 5m and 1h cache writes distinctly (provider-specific, §5.2)."""
    card = resolve_card(default_pricebook(), provider="anthropic", model="claude-3-5-haiku", at=_AT)
    assert card is not None
    assert TokenClass.CACHE_READ in card.usd_per_mtok
    assert TokenClass.CACHE_WRITE_5M in card.usd_per_mtok
    assert TokenClass.CACHE_WRITE_1H in card.usd_per_mtok


def test_dated_or_suffixed_model_id_resolves_to_its_family() -> None:
    """A dated id (claude-3-5-haiku-20241022) resolves to the claude-3-5-haiku family card."""
    book = default_pricebook()
    exact = resolve_card(book, provider="anthropic", model="claude-3-5-haiku", at=_AT)
    dated = resolve_card(book, provider="anthropic", model="claude-3-5-haiku-20241022", at=_AT)
    assert dated is not None
    assert exact is not None
    assert dated.model == exact.model  # the suffixed id mapped to the same family card


def test_unknown_model_stays_honestly_unpriced() -> None:
    """A model no family card matches returns None (never a fabricated /bin/zsh price)."""
    book = default_pricebook()
    assert resolve_card(book, provider="openai", model="totally-made-up", at=_AT) is None
    # an unknown provider is likewise unpriced
    assert resolve_card(book, provider="cohere", model="command-r", at=_AT) is None


def test_ingest_prices_dated_model_id_via_family_prefix() -> None:
    """span_to_cost_event prices a DATED model id (claude-3-5-haiku-20241022) from the family.

    Anthropic always emits dated ids; the ingest path must resolve them to the family
    card, not miss on exact-match. (Regression: the server priced gemini but not the
    dated anthropic id, because the path used exact card_for instead of the resolver.)
    """
    from uuid import uuid4

    from valuemaxx.capture.otlp.otlp_ingest import span_to_cost_event
    from valuemaxx.core.ids import TenantId

    class _Clock:
        def now(self) -> datetime:
            return _AT

    attrs: dict[str, object] = {
        "gen_ai.system": "anthropic",
        "gen_ai.request.model": "claude-3-5-haiku-20241022",  # dated suffix
        "gen_ai.usage.input_tokens": 1_000_000,
        "gen_ai.usage.output_tokens": 1_000_000,
    }
    event = span_to_cost_event(
        attrs, tenant_id=TenantId(uuid4()), pricebook=default_pricebook(), clock=_Clock()
    )
    # claude-3-5-haiku: 1M input @0.80 + 1M output @4.00 = 4.80
    assert event.cost_usd == Decimal("4.800000")


def test_default_priced_span_is_estimated_not_measured() -> None:
    """A cost computed from the default pricebook is labeled ESTIMATED, never MEASURED.

    The honesty axes forbid laundering an estimate into a billing-grade cost. The server
    prices third-party spans with the default snapshot book, so those CostEvents must
    carry ``estimated`` provenance — proven here through the real ingest entry point.
    """
    from uuid import uuid4

    from valuemaxx.capture.otlp.otlp_ingest import span_to_cost_event
    from valuemaxx.core.enums import Provenance
    from valuemaxx.core.ids import TenantId

    class _Clock:
        def now(self) -> datetime:
            return _AT

    attrs: dict[str, object] = {
        "gen_ai.system": "anthropic",
        "gen_ai.request.model": "claude-3-5-haiku",
        "gen_ai.usage.input_tokens": 1000,
        "gen_ai.usage.output_tokens": 250,
    }
    event = span_to_cost_event(
        attrs,
        tenant_id=TenantId(uuid4()),
        pricebook=default_pricebook(),
        clock=_Clock(),
        default_provenance=Provenance.ESTIMATED,
    )
    assert event.cost_usd is not None  # the default book priced it
    assert event.provenance.provenance is Provenance.ESTIMATED  # never laundered to measured


def test_resolve_card_prefers_exact_over_family_prefix() -> None:
    """If both an exact card and a shorter-prefix family card exist, exact wins."""
    book = default_pricebook()
    # gemini-2.5-flash and gemini-2.5-flash-lite are distinct cards; the lite id must not
    # collapse onto the non-lite card.
    flash = resolve_card(book, provider="google", model="gemini-2.5-flash", at=_AT)
    lite = resolve_card(book, provider="google", model="gemini-2.5-flash-lite", at=_AT)
    assert flash is not None
    assert lite is not None
    assert lite.model == "gemini-2.5-flash-lite"
    # lite is cheaper than full flash — proves we didn't collapse lite onto flash.
    assert lite.usd_per_mtok[TokenClass.OUTPUT] < flash.usd_per_mtok[TokenClass.OUTPUT]
