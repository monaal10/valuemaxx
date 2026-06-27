"""PG4 — decode an OTLP span attribute mapping into a typed CostEvent (§5.2, H3).

This is the universal/TS ingest path: any language emits an OTLP span carrying the
``semconv`` keys, and ``span_to_cost_event`` maps it to a
:class:`~valuemaxx.core.cost.CostEvent`. Every key is read through a ``semconv``
constant — never an inline literal — so the wire contract has exactly one source
of truth (asserted by ``test_otlp_ingest_references_only_semconv_constants``).

``tenant_id`` is a MANDATORY keyword-only parameter (no anonymous events, §3.2).
An authoritative inline ``ai_margin.cost_usd`` (e.g. a gateway's ``usage.cost``)
is used as-is when present; otherwise cost is computed from the token vector
against the pricebook via the PG1 math.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from valuemaxx.capture.invariants import check_invariants, price_or_abort
from valuemaxx.capture.otlp import semconv
from valuemaxx.core.cost import CostEvent
from valuemaxx.core.enums import CaptureGranularity, Provenance
from valuemaxx.core.ids import AttemptId, CostEventId, RunId
from valuemaxx.core.provenance import ProvenanceLabel
from valuemaxx.core.tokens import TokenVector

if TYPE_CHECKING:
    from collections.abc import Mapping

    from valuemaxx.core.context import Clock
    from valuemaxx.core.ids import TenantId
    from valuemaxx.core.pricing import PriceBook


def _int_attr(attrs: Mapping[str, object], key: str) -> int:
    value = attrs.get(key)
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(value, 0)
    return 0


def _str_attr(attrs: Mapping[str, object], key: str, *, default: str = "") -> str:
    value = attrs.get(key)
    return value if isinstance(value, str) else default


def _bool_attr(attrs: Mapping[str, object], key: str) -> bool:
    return attrs.get(key) is True


def span_to_cost_event(
    attrs: Mapping[str, object],
    *,
    tenant_id: TenantId,
    pricebook: PriceBook | None,
    clock: Clock,
) -> CostEvent:
    """Decode an OTLP span's attribute mapping into a CostEvent (tenant scope required).

    The token vector is rebuilt from the standard input/output totals plus the
    ``ai_margin.*`` cache/reasoning extensions. Cost is the authoritative inline
    value when the span carries one, else the computed token x price (PG1).
    """
    total_input = _int_attr(attrs, semconv.GEN_AI_USAGE_INPUT_TOKENS)
    cache_read = _int_attr(attrs, semconv.AI_MARGIN_CACHE_READ)
    cache_write_5m = _int_attr(attrs, semconv.AI_MARGIN_CACHE_WRITE_5M)
    cache_write_1h = _int_attr(attrs, semconv.AI_MARGIN_CACHE_WRITE_1H)
    output = _int_attr(attrs, semconv.GEN_AI_USAGE_OUTPUT_TOKENS)
    reasoning = _int_attr(attrs, semconv.AI_MARGIN_REASONING)

    tokens = TokenVector.from_provider(
        total_input=total_input,
        cache_read=cache_read,
        cache_write_5m=cache_write_5m,
        cache_write_1h=cache_write_1h,
        output=output,
        reasoning=reasoning,
    )

    provider = _str_attr(attrs, semconv.GEN_AI_SYSTEM)
    model = _str_attr(attrs, semconv.GEN_AI_REQUEST_MODEL)
    granularity = (
        CaptureGranularity.PER_ATTEMPT
        if _str_attr(attrs, semconv.AI_MARGIN_CAPTURE_GRANULARITY) != CaptureGranularity.PER_CALL
        else CaptureGranularity.PER_CALL
    )

    inline_cost = attrs.get(semconv.AI_MARGIN_COST_USD)
    warnings: tuple[str, ...]
    if inline_cost is not None:
        # an authoritative inline cost (gateway usage.cost) is used as-is, never recomputed.
        cost_usd: Decimal | None = Decimal(str(inline_cost))
        warnings = ()
    else:
        card = (
            pricebook.card_for(provider=provider, model=model, at=clock.now())
            if pricebook is not None
            else None
        )
        cost_usd, billing_warnings = price_or_abort(
            tokens, card, billing_uncertain=False, provisioned_throughput=False
        )
        warnings = (*check_invariants(tokens, provider=provider), *billing_warnings)

    return CostEvent(
        tenant_id=tenant_id,
        id=CostEventId(
            f"{_str_attr(attrs, semconv.AI_MARGIN_RUN_ID)}:"
            f"{_str_attr(attrs, semconv.AI_MARGIN_ATTEMPT_ID)}"
        ),
        run_id=RunId(_str_attr(attrs, semconv.AI_MARGIN_RUN_ID)),
        attempt_id=AttemptId(_str_attr(attrs, semconv.AI_MARGIN_ATTEMPT_ID)),
        provider=provider,
        model=model,
        tokens=tokens,
        capture_granularity=granularity,
        provenance=ProvenanceLabel(provenance=Provenance.MEASURED),
        cost_usd=cost_usd,
        is_streaming=_bool_attr(attrs, semconv.AI_MARGIN_IS_STREAMING),
        partial_recovered=_bool_attr(attrs, semconv.AI_MARGIN_PARTIAL_RECOVERED),
        billing_uncertain_abort=cost_usd is None,
        provenance_warnings=warnings,
        occurred_at=clock.now(),
    )


__all__ = ["span_to_cost_event"]
