"""PG4 — OTLP span -> CostEvent ingest, mapped via semconv constants only (§5.2).

``span_to_cost_event`` decodes a span attribute mapping into a typed
:class:`~valuemaxx.core.cost.CostEvent`, reading every key through the
``semconv`` constants (never inline string literals). ``tenant_id`` is a
MANDATORY keyword (no anonymous events, §3.2). An authoritative inline
``ai_margin.cost_usd`` is used as-is when present (gateway provenance);
otherwise cost is computed from the token vector against the pricebook.
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from valuemaxx.capture.otlp import semconv
from valuemaxx.capture.otlp.otlp_ingest import span_to_cost_event
from valuemaxx.core.enums import CaptureGranularity, Provenance, TokenClass
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
                model="claude-opus-4-8",
                usd_per_mtok={
                    TokenClass.INPUT_UNCACHED: Decimal("15"),
                    TokenClass.OUTPUT: Decimal("75"),
                },
                effective_from=_AT,
                rule_version="v1",
            ),
        )
    )


def _span_attrs(**overrides: object) -> dict[str, object]:
    attrs: dict[str, object] = {
        semconv.GEN_AI_SYSTEM: "anthropic",
        semconv.GEN_AI_REQUEST_MODEL: "claude-opus-4-8",
        semconv.GEN_AI_USAGE_INPUT_TOKENS: 1_000_000,
        semconv.GEN_AI_USAGE_OUTPUT_TOKENS: 1_000_000,
        semconv.AI_MARGIN_CACHE_READ: 0,
        semconv.AI_MARGIN_CACHE_WRITE_5M: 0,
        semconv.AI_MARGIN_CACHE_WRITE_1H: 0,
        semconv.AI_MARGIN_REASONING: 0,
        semconv.AI_MARGIN_RUN_ID: "run-1",
        semconv.AI_MARGIN_ATTEMPT_ID: "att-1",
        semconv.AI_MARGIN_CAPTURE_GRANULARITY: "per_attempt",
        semconv.AI_MARGIN_IS_STREAMING: False,
        semconv.AI_MARGIN_PARTIAL_RECOVERED: False,
    }
    attrs.update(overrides)
    return attrs


def test_tenant_id_is_mandatory_keyword() -> None:
    """test_tenant_id_is_mandatory_keyword: there is no positional/anonymous tenant path."""
    import inspect

    sig = inspect.signature(span_to_cost_event)
    assert sig.parameters["tenant_id"].kind is inspect.Parameter.KEYWORD_ONLY


def test_span_round_trip_to_cost_event() -> None:
    """test_span_round_trip_to_cost_event: a span decodes into a valid CostEvent."""
    event = span_to_cost_event(
        _span_attrs(),
        tenant_id=_TENANT,
        pricebook=_pricebook(),
        clock=_FixedClock(),
    )
    assert event.tenant_id == _TENANT
    assert event.run_id == "run-1"
    assert event.attempt_id == "att-1"
    assert event.provider == "anthropic"
    assert event.model == "claude-opus-4-8"
    assert event.tokens.input_uncached == 1_000_000
    assert event.tokens.output == 1_000_000
    assert event.capture_granularity is CaptureGranularity.PER_ATTEMPT
    # computed cost: 1M input @15 + 1M output @75 = 90
    assert event.cost_usd == Decimal("90.000000")
    assert event.provenance.provenance is Provenance.MEASURED


def test_authoritative_inline_cost_used_when_present() -> None:
    """test_authoritative_inline_cost_used_when_present: ai_margin.cost_usd is used as-is."""
    event = span_to_cost_event(
        _span_attrs(**{semconv.AI_MARGIN_COST_USD: "0.001234"}),
        tenant_id=_TENANT,
        pricebook=_pricebook(),
        clock=_FixedClock(),
    )
    assert event.cost_usd == Decimal("0.001234")  # not the token x price computation


def test_streaming_flags_decoded() -> None:
    """test_streaming_flags_decoded: is_streaming / partial_recovered carried through."""
    event = span_to_cost_event(
        _span_attrs(
            **{
                semconv.AI_MARGIN_IS_STREAMING: True,
                semconv.AI_MARGIN_PARTIAL_RECOVERED: True,
            }
        ),
        tenant_id=_TENANT,
        pricebook=_pricebook(),
        clock=_FixedClock(),
    )
    assert event.is_streaming is True
    assert event.partial_recovered is True


def test_otlp_ingest_references_only_semconv_constants() -> None:
    """test_otlp_ingest_references_only_semconv_constants: no inline gen_ai./ai_margin. literals.

    The single-source-of-truth guarantee (H3): otlp_ingest must reference keys via
    the semconv constants, never by re-typing the literal string — otherwise the
    two could drift. We AST-scan the module for any string literal beginning with a
    wire-key prefix and assert there are none (all such literals live in semconv).
    """
    src = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "valuemaxx"
        / "capture"
        / "otlp"
        / "otlp_ingest.py"
    ).read_text()
    tree = ast.parse(src)
    offenders = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and (node.value.startswith("gen_ai.") or node.value.startswith("ai_margin."))
    ]
    assert offenders == [], f"otlp_ingest re-types wire-key literals: {offenders}"
