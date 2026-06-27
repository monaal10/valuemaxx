"""DRYRUN — preview cost-per-outcome via an injected rollup reader (design §7 / C3).

:func:`dry_run` previews the cost-per-outcome a proposed rule would produce, by
consulting a :class:`MetricsRollupReader` — a narrow Protocol whose real
implementation is backed by the metrics/store packages and **injected** at the
service boundary. The onboarding package codes against this Protocol only; it never
imports ``valuemaxx.metrics`` or ``valuemaxx.store`` (the ``no_raw_source_exfil`` /
dependency-direction discipline, asserted by ``test_onboarding_imports_no_surface_\
or_concrete_store``).

The returned :class:`~valuemaxx.onboarding.capabilities.DryRunPreview` always carries
BOTH H7 confidence fields (``minimum_tier`` + ``confidence_distribution``), so a
preview can never collapse the confidence (§3.1). When no outcomes are bound yet, the
cost is None (never a fabricated zero) and the confidence is the most-conservative
``likely`` with an empty distribution.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from valuemaxx.core import BindingTier
from valuemaxx.onboarding.capabilities import DryRunPreview

if TYPE_CHECKING:
    from valuemaxx.onboarding.capabilities import CostPerOutcome


@runtime_checkable
class MetricsRollupReader(Protocol):
    """The injected seam for reading a cost-per-outcome rollup (real impl at G4/G5).

    Implementations are backed by the metrics/store packages; onboarding depends on
    this Protocol, never a concrete reader, so it carries no off-box data path.
    """

    def cost_per_outcome(self, *, outcome_name: str) -> CostPerOutcome | None:
        """Return the cost-per-outcome rollup for ``outcome_name``, or None if unbound."""
        ...


# The conservative confidence used when nothing is bound yet: a single 'likely'
# placeholder so both H7 fields are present and the headline is the least-trusted tier.
_EMPTY_DISTRIBUTION = {BindingTier.LIKELY: 1}


def dry_run(outcome_name: str, *, rollup_reader: MetricsRollupReader) -> DryRunPreview:
    """Preview the cost-per-outcome for ``outcome_name`` via the injected reader.

    Returns a :class:`DryRunPreview` carrying both H7 fields. When the reader has no
    rollup (no bound outcomes), the cost is None and the confidence is the most
    conservative ``likely`` — never a fabricated number.
    """
    result = rollup_reader.cost_per_outcome(outcome_name=outcome_name)
    if result is None:
        return DryRunPreview(
            outcome_name=outcome_name,
            cost_per_outcome_usd=None,
            minimum_tier=BindingTier.LIKELY,
            confidence_distribution=dict(_EMPTY_DISTRIBUTION),
        )
    return DryRunPreview(
        outcome_name=outcome_name,
        cost_per_outcome_usd=result.cost_usd,
        minimum_tier=result.minimum_tier,
        confidence_distribution=dict(result.confidence_distribution),
    )


__all__ = ["MetricsRollupReader", "dry_run"]
