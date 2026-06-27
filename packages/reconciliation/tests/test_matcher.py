"""Match-key grouping — the proration unit of (provider, project, model, class, day)."""

from __future__ import annotations

import pytest
from valuemaxx.reconciliation.matcher import group_by_match_key, match_key_of, parse_match_key


def test_match_key_format() -> None:
    """The match key is the pipe-joined 5-tuple in canonical order."""
    key = match_key_of(
        provider="anthropic",
        project="proj-1",
        model="claude-sonnet-4",
        token_class="input_uncached",
        day="2026-06-27",
    )
    assert key == "anthropic|proj-1|claude-sonnet-4|input_uncached|2026-06-27"


def test_parse_match_key_round_trips_to_tuple() -> None:
    """parse_match_key inverts match_key_of into the core 5-tuple."""
    key = match_key_of(
        provider="openai",
        project="ws-2",
        model="gpt-5",
        token_class="output",
        day="2026-06-01",
    )
    assert parse_match_key(key) == ("openai", "ws-2", "gpt-5", "output", "2026-06-01")


def test_group_by_match_key_buckets_items() -> None:
    """Items sharing a key land in one bucket, preserving input order."""
    items = [
        ("a", "anthropic|p|m|output|2026-06-27"),
        ("b", "openai|p|m|output|2026-06-27"),
        ("c", "anthropic|p|m|output|2026-06-27"),
    ]
    grouped = group_by_match_key(items, key=lambda pair: pair[1])
    assert set(grouped) == {
        "anthropic|p|m|output|2026-06-27",
        "openai|p|m|output|2026-06-27",
    }
    assert grouped["anthropic|p|m|output|2026-06-27"] == [
        ("a", "anthropic|p|m|output|2026-06-27"),
        ("c", "anthropic|p|m|output|2026-06-27"),
    ]


def test_group_by_match_key_empty() -> None:
    """Grouping nothing yields an empty mapping."""
    assert group_by_match_key([], key=lambda x: str(x)) == {}


def test_parse_match_key_wrong_arity_raises() -> None:
    """A key without exactly five parts is rejected."""
    with pytest.raises(ValueError, match="exactly 5"):
        parse_match_key("only|three|parts")
