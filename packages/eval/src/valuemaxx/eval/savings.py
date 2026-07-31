"""What switching a model would actually cost — the missing half of a recommendation.

An eval could say "this candidate holds parity" and never say "…and it is 92% cheaper
per outcome". Both numbers existed in the system; nothing multiplied them, so the one
sentence a user wants — *switch and save X%* — could not be produced.

The honest construction is to REPRICE the incumbent's own observed traffic. We take the
token vectors the incumbent actually produced and price them against the candidate's
card, so the comparison is over this tenant's real prompt/response shape rather than a
vendor's headline rate. A workload that is 90% cached input has a completely different
delta from one that is output-heavy, and a naive rate-card ratio would be wrong for
both.

Three honesty properties, each pinned by a test:

* **Same tokens, two prices.** The candidate is priced on the incumbent's measured
  token mix. We do NOT assume the candidate would emit the same number of tokens — it
  is an estimate of the same work at a different rate, and the type says so.
* **An unpriceable model yields no estimate.** A missing price card returns None with a
  reason, never a zero. "$0.00 saved" and "we could not price this" are different
  facts, and rendering the second as the first invents a number.
* **The estimate is labelled ESTIMATED, never measured.** It is arithmetic over a list
  price applied to traffic the candidate never actually served. Only a real reconciled
  invoice is measured, and nothing here may claim that.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from valuemaxx.core import CostEvent
    from valuemaxx.core.pricing import PriceBook, PriceCard
    from valuemaxx.core.tokens import TokenVector


class CostPricer(Protocol):
    """Prices a token vector against a card.

    INJECTED rather than imported: `valuemaxx.capture` owns the pricing arithmetic, and
    the logic packages are contractually independent (import-linter enforces it), so
    reaching across would couple two siblings that must stay swappable. The app already
    wires capture's `compute_cost_usd` here.
    """

    def __call__(self, tokens: TokenVector, card: PriceCard) -> tuple[Decimal, tuple[str, ...]]:
        """Return ``(cost_usd, warnings)`` for ``tokens`` priced by ``card``."""
        ...


@dataclass(frozen=True, slots=True)
class SwitchEstimate:
    """The projected cost of serving the SAME traffic with a different model.

    ``incumbent_usd`` is what the tenant actually spent on the priced events;
    ``candidate_usd`` is those same token vectors repriced against the candidate's
    card. ``pct_change`` is negative for a saving.
    """

    incumbent_model: str
    candidate_model: str
    incumbent_usd: Decimal
    candidate_usd: Decimal
    """Events the estimate covers — a caller can see how thin the sample is."""
    event_count: int

    @property
    def delta_usd(self) -> Decimal:
        """Candidate minus incumbent: negative is a saving."""
        return self.candidate_usd - self.incumbent_usd

    @property
    def pct_change(self) -> Decimal | None:
        """Percent change vs the incumbent, or None when the incumbent cost nothing.

        A zero baseline has no meaningful percentage — dividing would be a crash or a
        fabricated infinity, and "100% cheaper than free" is not a claim worth making.
        """
        if self.incumbent_usd == 0:
            return None
        return (self.delta_usd / self.incumbent_usd) * Decimal(100)


@dataclass(frozen=True, slots=True)
class SwitchEstimateResult:
    """An estimate, or the reason there isn't one."""

    estimate: SwitchEstimate | None
    reason: str | None = None


def estimate_switch(
    events: Sequence[CostEvent],
    *,
    incumbent_model: str,
    candidate_model: str,
    candidate_provider: str,
    pricebook: PriceBook,
    price: CostPricer,
    at: datetime,
) -> SwitchEstimateResult:
    """Reprice the incumbent's observed traffic against a candidate model.

    Only events actually served by ``incumbent_model`` are considered: repricing
    another model's traffic would answer a question nobody asked. Returns a reason
    rather than a number whenever the estimate would be invented.
    """
    incumbent_events = [e for e in events if e.model == incumbent_model]
    if not incumbent_events:
        return SwitchEstimateResult(
            estimate=None,
            reason=f"no captured traffic for {incumbent_model!r} to reprice",
        )

    candidate_card = pricebook.card_for(provider=candidate_provider, model=candidate_model, at=at)
    if candidate_card is None:
        # A missing card is not a zero. Pretending it is would report a 100% saving for
        # a model we simply do not know the price of.
        return SwitchEstimateResult(
            estimate=None,
            reason=(
                f"no price card for {candidate_provider}/{candidate_model}; cannot "
                "estimate the cost of switching"
            ),
        )

    incumbent_usd = Decimal(0)
    candidate_usd = Decimal(0)
    priced = 0
    for event in incumbent_events:
        if event.cost_usd is None:
            # An unpriced incumbent event has no baseline to compare against; counting
            # it as free would understate what the tenant spends today.
            continue
        candidate_cost, _warnings = price(event.tokens, candidate_card)
        incumbent_usd += event.cost_usd
        candidate_usd += candidate_cost
        priced += 1

    if priced == 0:
        return SwitchEstimateResult(
            estimate=None,
            reason=f"{len(incumbent_events)} event(s) for {incumbent_model!r} carry no cost",
        )

    return SwitchEstimateResult(
        estimate=SwitchEstimate(
            incumbent_model=incumbent_model,
            candidate_model=candidate_model,
            incumbent_usd=incumbent_usd,
            candidate_usd=candidate_usd,
            event_count=priced,
        )
    )


__all__ = ["CostPricer", "SwitchEstimate", "SwitchEstimateResult", "estimate_switch"]
