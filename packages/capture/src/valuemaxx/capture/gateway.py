"""PG5 — gateway cost sources: OpenRouter authoritative inline usage.cost (§5.5).

OpenRouter returns the actual billed ``usage.cost`` inline with no markup — an
authoritative spend source. We tag the resulting CostEvent ``provider_reconciled``
(reconciled at source) and link it to the gateway transaction id as its
reconciliation record. The OpenRouter ``user`` field carries run attribution, so
``user`` -> ``run_id``.

**Design law (§5.5):** we only take a cost source that yields authoritative billed
cost or properly-reconciled actuals; we NEVER ship a vendor self-declared estimate
as spend. A response that flags its own cost as an estimate is refused with a
:class:`~valuemaxx.core.errors.ProvenanceWarning`, never silently recorded.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, cast

from valuemaxx.core.cost import CostEvent
from valuemaxx.core.enums import CaptureGranularity, Provenance
from valuemaxx.core.errors import ProvenanceWarning
from valuemaxx.core.ids import AttemptId, CostEventId, RunId
from valuemaxx.core.provenance import ProvenanceLabel
from valuemaxx.core.tokens import TokenVector

if TYPE_CHECKING:
    from collections.abc import Mapping

    from valuemaxx.core.context import Clock
    from valuemaxx.core.ids import TenantId


class OpenRouterSource:
    """A cost source for OpenRouter responses (authoritative inline ``usage.cost``)."""

    def __init__(self, *, clock: Clock) -> None:
        self._clock = clock

    @property
    def name(self) -> str:
        """The cost-source identifier (used by ``list_cost_sources``)."""
        return "gateway:openrouter"

    def to_cost_event(self, response: Mapping[str, object], *, tenant_id: TenantId) -> CostEvent:
        """Decode an OpenRouter response into a ``provider_reconciled`` CostEvent.

        Raises :class:`ProvenanceWarning` if the response self-declares its cost as
        an estimate — a vendor estimate is never an authoritative spend source.
        """
        usage = response.get("usage")
        if not isinstance(usage, dict):
            raise ProvenanceWarning("OpenRouter response has no usage object; cannot record cost")
        usage_map = cast("Mapping[str, object]", usage)

        if usage_map.get("is_estimate") is True:
            raise ProvenanceWarning(
                "OpenRouter response self-declares cost as an estimate; refusing to record it as "
                "spend (design law §5.5: never ship vendor-estimated cost as a spend source)"
            )

        cost_raw = usage_map.get("cost")
        if cost_raw is None:
            raise ProvenanceWarning("OpenRouter response carries no authoritative usage.cost")
        cost_usd = Decimal(str(cost_raw))

        prompt_tokens = _as_int(usage_map.get("prompt_tokens"))
        completion_tokens = _as_int(usage_map.get("completion_tokens"))
        tokens = TokenVector(
            input_uncached=prompt_tokens,
            cache_read=0,
            cache_write_5m=0,
            cache_write_1h=0,
            output=completion_tokens,
            reasoning=0,
        )

        gen_id = _as_str(response.get("id"))
        run_id = RunId(_as_str(response.get("user")))
        record_id = f"gateway:openrouter:{gen_id}"

        return CostEvent(
            tenant_id=tenant_id,
            id=CostEventId(f"openrouter:{gen_id}"),
            run_id=run_id,
            attempt_id=AttemptId(gen_id),
            provider="openrouter",
            model=_as_str(response.get("model")),
            tokens=tokens,
            capture_granularity=CaptureGranularity.PER_ATTEMPT,
            provenance=ProvenanceLabel(
                provenance=Provenance.PROVIDER_RECONCILED,
                reconciliation_record_id=record_id,
                note="authoritative inline usage.cost (gateway/provider provenance)",
            ),
            cost_usd=cost_usd,
            is_streaming=False,
            partial_recovered=False,
            billing_uncertain_abort=False,
            provenance_warnings=(),
            occurred_at=self._clock.now(),
        )


def _as_int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(value, 0)
    return 0


def _as_str(value: object) -> str:
    return value if isinstance(value, str) else ""


__all__ = ["OpenRouterSource"]
