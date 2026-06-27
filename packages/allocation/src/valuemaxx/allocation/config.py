"""shared_costs.yaml intake — the declared-key allocation config (§5.4).

Shared COGS that aren't directly measured (a vector DB, an idle GPU pool, a platform
license) are declared in ``shared_costs.yaml`` with the tier they belong to and, for
Tier-2, the *allocation key* by which they're split proportionally. When the file is
absent we fall back to **Tier-1-only mode**: only directly-measured cost is published
and ``pct_unallocated`` is surfaced prominently (§5.4) rather than smearing an
unmeasured guess.

``SharedCostInput`` / ``SharedCostsConfig`` are config-parse envelopes (this file is
on the ``no_type_outside_core`` config-AST allowlist) — the authoritative domain
artifacts (``AllocatedLine``, ``AllocatedRollup``) live only in ``valuemaxx.core``.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, cast

import yaml
from pydantic import model_validator
from valuemaxx.core import AllocationTier
from valuemaxx.core.base import StrictModel, TenantScopedModel

if TYPE_CHECKING:
    from collections.abc import Sequence

    from valuemaxx.core import TenantId


class SharedCostInput(StrictModel):
    """One declared shared-cost line from ``shared_costs.yaml``.

    Attributes:
        name: a human label for the shared cost.
        amount_usd: the total shared cost to allocate (exact Decimal).
        tier: the allocation tier (Tier-2 ``shared_proportional`` or Tier-3
            ``fixed_overhead``; Tier-1 ``direct`` is never declared here — it comes
            from measured cost events).
        allocation_key: for Tier-2, the declared key the cost is split by (required).
        is_idle_gpu: for Tier-3, whether this is idle-GPU capacity (quarantined beside
            the unit cost, never smeared into the fully-loaded number).
        rule_version: the version of the allocation rule that produced this input.
        sensitivity_pct: optional sensitivity of the allocation to its key.
    """

    name: str
    amount_usd: Decimal
    tier: AllocationTier
    allocation_key: str | None = None
    is_idle_gpu: bool = False
    rule_version: str | None = None
    sensitivity_pct: Decimal | None = None

    @model_validator(mode="after")
    def _check(self) -> SharedCostInput:
        """Tier-2 requires an allocation_key; Tier-1 is never declared as shared cost."""
        if self.tier is AllocationTier.DIRECT:
            raise ValueError(
                "Tier-1 (direct) cost is measured from cost events, not declared in "
                "shared_costs.yaml"
            )
        if self.tier is AllocationTier.SHARED_PROPORTIONAL and self.allocation_key is None:
            raise ValueError(f"shared_proportional input {self.name!r} requires an allocation_key")
        if self.amount_usd < 0:
            raise ValueError(f"shared cost {self.name!r} amount must be non-negative")
        return self


class SharedCostsConfig(TenantScopedModel):
    """The parsed shared_costs.yaml for a tenant (possibly empty = Tier-1-only)."""

    inputs: tuple[SharedCostInput, ...] = ()

    @property
    def is_tier1_only(self) -> bool:
        """True when no shared costs are declared — publish Tier-1 (measured) only."""
        return len(self.inputs) == 0

    def inputs_for_tier(self, tier: AllocationTier) -> Sequence[SharedCostInput]:
        """The declared inputs belonging to the given tier."""
        return [i for i in self.inputs if i.tier is tier]


def load_shared_costs(text: str, *, tenant_id: TenantId) -> SharedCostsConfig:
    """Parse ``shared_costs.yaml`` text into a :class:`SharedCostsConfig`.

    An absent or blank document yields an empty config (Tier-1-only mode), never an
    error — the absence of shared-cost declarations is a valid, honest state.

    Args:
        text: the raw yaml text (may be empty).
        tenant_id: the tenant the config belongs to.

    Returns:
        The parsed :class:`SharedCostsConfig`.

    Raises:
        ValueError: if a declared input is malformed (bad tier, missing allocation_key,
            negative amount).
    """
    raw: object = yaml.safe_load(text) if text.strip() else None
    if raw is None:
        return SharedCostsConfig(tenant_id=tenant_id, inputs=())
    if not isinstance(raw, dict):
        # ValueError (not TypeError): malformed config is a value problem, and
        # load_shared_costs raises ValueError uniformly for every config defect.
        raise ValueError("shared_costs.yaml must be a mapping with a 'shared_costs' list")  # noqa: TRY004
    body = cast("dict[str, object]", raw)
    entries: object = body.get("shared_costs", [])
    if not isinstance(entries, list):
        raise ValueError("'shared_costs' must be a list")  # noqa: TRY004 — malformed config is a ValueError
    items = cast("list[object]", entries)
    inputs = tuple(_parse_input(entry) for entry in items)
    return SharedCostsConfig(tenant_id=tenant_id, inputs=inputs)


def _parse_input(entry: object) -> SharedCostInput:
    """Validate one raw yaml entry, coercing the tier string to ``AllocationTier``.

    The model is strict (no silent coercion), so the ``tier`` string and ``amount_usd``
    are normalised here at the parse boundary before strict validation.
    """
    if not isinstance(entry, dict):
        raise ValueError("each shared_costs entry must be a mapping")  # noqa: TRY004 — malformed config is a ValueError
    mapping = cast("dict[object, object]", entry)
    data: dict[str, object] = {str(k): v for k, v in mapping.items()}
    tier_raw = data.get("tier")
    if not isinstance(tier_raw, str):
        raise ValueError("each shared_costs entry must declare a string 'tier'")  # noqa: TRY004 — malformed config is a ValueError
    try:
        data["tier"] = AllocationTier(tier_raw)
    except ValueError as exc:
        raise ValueError(f"unknown allocation tier {tier_raw!r}") from exc
    # Strict model: normalise money to exact Decimal at the parse boundary (never float).
    if "amount_usd" in data:
        data["amount_usd"] = _to_decimal(data["amount_usd"], field="amount_usd")
    if data.get("sensitivity_pct") is not None:
        data["sensitivity_pct"] = _to_decimal(data["sensitivity_pct"], field="sensitivity_pct")
    return SharedCostInput.model_validate(data)


def _to_decimal(value: object, *, field: str) -> Decimal:
    """Coerce a yaml scalar to exact Decimal via its string form (never via float)."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (str, int)):
        try:
            return Decimal(value)
        except ArithmeticError as exc:
            raise ValueError(f"{field} {value!r} is not a valid decimal") from exc
    raise ValueError(f"{field} must be a decimal string or integer, not {type(value).__name__}")


__all__ = ["SharedCostInput", "SharedCostsConfig", "load_shared_costs"]
