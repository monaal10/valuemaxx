"""PG1 — token invariants (lenient warnings) + the billing-honesty abort gate (§5.2).

Two responsibilities:

``check_invariants`` is the *lenient, OTLP-coerced* path: a parsed usage object
may be borderline, and we must never crash the host nor silently drop a number.
It returns a tuple of human-readable provenance warnings for any violated
provider-shape invariant (e.g. OpenAI reporting cache-write tokens it does not
bill). It NEVER raises and NEVER returns silently-swallowed state.

``price_or_abort`` is the *billing-honesty* gate. When billing is genuinely
uncertain we refuse to fabricate ``token x price``:
  * **provisioned throughput** (PTU): the per-token rate does not reflect actual
    spend, so cost is ``None`` (H10/§13);
  * **client abort** / billing_uncertain: the attempt may not be billed as
    metered, so cost is ``None``;
  * **no price card**: an unknown (provider, model) cannot be priced, so ``None``.

In every abort case the returned warnings carry ``billing_uncertain_abort`` so the
CostEvent records *why* it has no cost, never leaving a silent zero or a guess.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from valuemaxx.capture.pricing import compute_cost_usd

if TYPE_CHECKING:
    from decimal import Decimal

    from valuemaxx.core.pricing import PriceCard
    from valuemaxx.core.tokens import TokenVector

PROVISIONED_THROUGHPUT_REASON = "provisioned_throughput"
"""The billing_uncertain_abort reason for a provisioned-throughput (PTU) attempt."""

_BILLING_UNCERTAIN = "billing_uncertain_abort"

# Providers that do NOT bill a distinct cache-write token class. Reporting
# cache-write tokens for one of these is a provider-shape inconsistency we warn on.
_NO_CACHE_WRITE_PROVIDERS = frozenset({"openai"})


def check_invariants(tokens: TokenVector, *, provider: str) -> tuple[str, ...]:
    """Return provenance warnings for any violated provider-shape invariant. Never raises.

    The structural invariants (non-negative counts, ``reasoning <= output``, cache
    tokens within ``total_input``) are enforced at :class:`TokenVector` construction
    already; this lenient checker adds the *provider-specific* shape warnings that
    are advisory rather than constructive errors.
    """
    warnings: list[str] = []
    if provider in _NO_CACHE_WRITE_PROVIDERS and (tokens.cache_write_5m or tokens.cache_write_1h):
        warnings.append(
            f"provider_shape: {provider} does not bill a distinct cache_write class but the "
            f"usage object reported cache_write tokens "
            f"(5m={tokens.cache_write_5m}, 1h={tokens.cache_write_1h})"
        )
    return tuple(warnings)


def price_or_abort(
    tokens: TokenVector,
    card: PriceCard | None,
    *,
    billing_uncertain: bool,
    provisioned_throughput: bool,
) -> tuple[Decimal | None, tuple[str, ...]]:
    """Price the attempt, or abort to ``None`` cost when billing is genuinely uncertain.

    Returns ``(cost_usd, provenance_warnings)``. ``cost_usd`` is ``None`` (never a
    fabricated token x price) when provisioned throughput is in effect, the attempt
    is a billing-uncertain client abort, or no price card is available — each case
    accompanied by a ``billing_uncertain_abort`` warning explaining the refusal.
    """
    if provisioned_throughput:
        return None, (
            f"{_BILLING_UNCERTAIN}: {PROVISIONED_THROUGHPUT_REASON} "
            "(per-token rate does not reflect actual spend; refusing token x price)",
        )
    if billing_uncertain:
        return None, (
            f"{_BILLING_UNCERTAIN}: client_abort "
            "(attempt may not be metered-billed; refusing token x price)",
        )
    if card is None:
        return None, (
            "no_price_card: no (provider, model) price card available; cannot price this attempt",
        )
    return compute_cost_usd(tokens, card)


__all__ = ["PROVISIONED_THROUGHPUT_REASON", "check_invariants", "price_or_abort"]
