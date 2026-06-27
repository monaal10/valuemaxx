"""F0-CORE-1a: TokenVector — the six enforced invariants (§5.2).

(1) all non-negative; (2) output >= reasoning (reasoning is embedded within
output); (3) cache <= total_input (via from_provider guard); (4) 5m/1h are
distinct fields, never one flat cache_write; (5) from_provider rejects (3);
(6) reasoning is derived/separate, never double-added into the input side.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError
from valuemaxx.core.tokens import TokenVector


def test_negative_rejected() -> None:
    """Invariant (1): any negative token count is rejected."""
    with pytest.raises(ValidationError):
        TokenVector(
            input_uncached=-1,
            cache_read=0,
            cache_write_5m=0,
            cache_write_1h=0,
            output=0,
            reasoning=0,
        )


def test_reasoning_le_output() -> None:
    """Invariant (2)/(6): reasoning must not exceed output (it is within output)."""
    with pytest.raises(ValidationError):
        TokenVector(
            input_uncached=0,
            cache_read=0,
            cache_write_5m=0,
            cache_write_1h=0,
            output=10,
            reasoning=11,
        )


def test_reasoning_equal_output_ok() -> None:
    tv = TokenVector(
        input_uncached=0,
        cache_read=0,
        cache_write_5m=0,
        cache_write_1h=0,
        output=10,
        reasoning=10,
    )
    assert tv.reasoning == tv.output == 10


def test_total_input_property() -> None:
    """Invariant: total_input = sum of the four input-side classes."""
    tv = TokenVector(
        input_uncached=100,
        cache_read=50,
        cache_write_5m=20,
        cache_write_1h=10,
        output=5,
        reasoning=2,
    )
    # total_input sums uncached + read + write_5m + write_1h (the input side);
    # output/reasoning are NOT part of input (invariant 6 — no double-add).
    assert tv.total_input == 100 + 50 + 20 + 10


def test_5m_and_1h_are_distinct_fields() -> None:
    """Invariant (4): 5m and 1h cache writes are distinct, round-trip separately."""
    tv = TokenVector(
        input_uncached=0,
        cache_read=0,
        cache_write_5m=7,
        cache_write_1h=11,
        output=0,
        reasoning=0,
    )
    assert tv.cache_write_5m == 7
    assert tv.cache_write_1h == 11
    dumped = tv.model_dump()
    assert dumped["cache_write_5m"] == 7
    assert dumped["cache_write_1h"] == 11
    assert "cache_write" not in dumped  # never one flat field


def test_from_provider_accepts_valid_cache() -> None:
    """Invariant (3)/(5): from_provider accepts cache <= total_input and derives uncached."""
    tv = TokenVector.from_provider(
        total_input=145,
        cache_read=30,
        cache_write_5m=10,
        cache_write_1h=5,
        output=8,
        reasoning=3,
    )
    assert tv.cache_read == 30
    # input_uncached is derived as the remainder: 145 - (30+10+5) = 100.
    assert tv.input_uncached == 100
    assert tv.total_input == 145


def test_from_provider_rejects_cache_exceeding_total_input() -> None:
    """Invariant (5): from_provider rejects cache > total_input (mis-parsed usage)."""
    with pytest.raises(ValueError, match="cache"):
        TokenVector.from_provider(
            total_input=5,
            cache_read=50,
            cache_write_5m=50,
            cache_write_1h=50,
            output=0,
            reasoning=0,
        )


def test_plain_constructor_does_not_apply_provider_cache_guard() -> None:
    """The plain constructor enforces (1),(2),(6) but not the provider cache guard.

    The cache<=total_input guard is a provider-shape rule applied only by
    from_provider; the internal model can hold reconciled/synthetic shapes.
    """
    tv = TokenVector(
        input_uncached=1,
        cache_read=2,
        cache_write_5m=3,
        cache_write_1h=4,
        output=0,
        reasoning=0,
    )
    assert tv.cache_read == 2


@given(
    input_uncached=st.integers(min_value=0, max_value=10_000),
    cache_read=st.integers(min_value=0, max_value=10_000),
    cache_write_5m=st.integers(min_value=0, max_value=10_000),
    cache_write_1h=st.integers(min_value=0, max_value=10_000),
    output=st.integers(min_value=0, max_value=10_000),
)
def test_round_trip_property(
    input_uncached: int,
    cache_read: int,
    cache_write_5m: int,
    cache_write_1h: int,
    output: int,
) -> None:
    """Invariant (round-trip): any valid vector survives model_dump_json round-trip."""
    tv = TokenVector(
        input_uncached=input_uncached,
        cache_read=cache_read,
        cache_write_5m=cache_write_5m,
        cache_write_1h=cache_write_1h,
        output=output,
        reasoning=min(output, output),  # reasoning <= output always
    )
    restored = TokenVector.model_validate_json(tv.model_dump_json())
    assert restored == tv
    assert restored.total_input == input_uncached + cache_read + cache_write_5m + cache_write_1h
