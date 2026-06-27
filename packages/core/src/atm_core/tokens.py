"""The token vector — usage split by class, with the six enforced invariants (§5.2).

Blending the input classes mis-prices the cached slice badly, so the vector is
*always* split by class: ``input_uncached / cache_read / cache_write_5m /
cache_write_1h / output / reasoning``. The 5m and 1h cache writes are DISTINCT
fields (never one flat ``cache_write``). ``reasoning`` is DERIVED and embedded
within ``output`` (count of ``type:"thinking"`` blocks), never a separate input.

The six invariants:
  1. all counts non-negative;
  2. ``output >= reasoning`` (reasoning lives inside output);
  3. cache tokens never exceed ``total_input`` (provider-shape guard);
  4. 5m/1h are distinct fields;
  5. :meth:`TokenVector.from_provider` rejects a violation of (3);
  6. ``reasoning`` is derived/separate, never double-added into the input side.

Invariants (1), (2), (6) are enforced on every construction; (3)/(5) are the
provider-shape guard applied by :meth:`from_provider` (the internal model may
hold reconciled/synthetic shapes that the raw provider object would not).
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, model_validator

from atm_core.base import StrictModel

_NonNegInt = Annotated[int, Field(ge=0)]


class TokenVector(StrictModel):
    """Per-attempt token usage, split by the six classes (§5.2)."""

    input_uncached: _NonNegInt
    cache_read: _NonNegInt
    cache_write_5m: _NonNegInt
    cache_write_1h: _NonNegInt
    output: _NonNegInt
    reasoning: _NonNegInt

    @model_validator(mode="after")
    def _reasoning_within_output(self) -> TokenVector:
        """Invariant (2)/(6): reasoning is embedded within output, never beyond it."""
        if self.reasoning > self.output:
            raise ValueError(
                f"reasoning ({self.reasoning}) must not exceed output ({self.output}); "
                "reasoning is derived and embedded within output (§5.2)"
            )
        return self

    @property
    def total_input(self) -> int:
        """Sum of the four input-side classes (output/reasoning are not input)."""
        return self.input_uncached + self.cache_read + self.cache_write_5m + self.cache_write_1h

    @classmethod
    def from_provider(
        cls,
        *,
        total_input: int,
        cache_read: int,
        cache_write_5m: int,
        cache_write_1h: int,
        output: int,
        reasoning: int,
    ) -> TokenVector:
        """Build a vector from a raw provider usage object, applying the cache guard.

        Providers report a single ``total_input`` token count plus the cache-token
        subsets; ``input_uncached`` is *derived* as the remainder. Invariant (3)/(5):
        the cache tokens (read + 5m write + 1h write) can never exceed ``total_input``
        on a real response — a violation means the usage object was mis-parsed, so we
        reject it rather than silently mis-pricing (which would surface as a negative
        uncached remainder otherwise).
        """
        cache_total = cache_read + cache_write_5m + cache_write_1h
        if cache_total > total_input:
            raise ValueError(
                f"cache tokens ({cache_total}) exceed total_input ({total_input}); "
                "provider usage object is inconsistent (§5.2 invariant 3)"
            )
        return cls(
            input_uncached=total_input - cache_total,
            cache_read=cache_read,
            cache_write_5m=cache_write_5m,
            cache_write_1h=cache_write_1h,
            output=output,
            reasoning=reasoning,
        )


__all__ = ["TokenVector"]
