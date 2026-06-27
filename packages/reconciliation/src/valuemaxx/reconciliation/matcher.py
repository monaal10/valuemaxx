"""Match-key grouping — the unit reconciliation prorates over (§5.3).

A reconciliation match key is ``(provider, project/workspace, model, token_class,
day)``: the finest grain at which a provider cost API reports an authoritative
total. Estimates are summed within a key, the billed total is fetched for that
key, and proration distributes the total across the key's per-request estimates.

The string form is the pipe-joined 5-tuple (stable, human-readable, and the index
key used by the store); :func:`parse_match_key` inverts it into the core
``ReconciliationRecord.match_key`` tuple.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

_SEP = "|"
_T = TypeVar("_T")


def match_key_of(
    *,
    provider: str,
    project: str,
    model: str,
    token_class: str,
    day: str,
) -> str:
    """Build the canonical pipe-joined match key for a reconciliation unit.

    Args:
        provider: the cost source (e.g. ``"anthropic"``, ``"openai"``).
        project: the project / workspace scope the provider bills by.
        model: the model id.
        token_class: the token class (one of the six, §5.2).
        day: the UTC billing day, ``YYYY-MM-DD``.

    Returns:
        ``"{provider}|{project}|{model}|{token_class}|{day}"``.
    """
    return _SEP.join((provider, project, model, token_class, day))


def parse_match_key(key: str) -> tuple[str, str, str, str, str]:
    """Invert :func:`match_key_of` into the 5-tuple used by ``ReconciliationRecord``.

    Raises:
        ValueError: if ``key`` does not have exactly five pipe-separated parts.
    """
    parts = key.split(_SEP)
    if len(parts) != 5:
        raise ValueError(
            f"match key {key!r} must have exactly 5 pipe-separated parts, got {len(parts)}"
        )
    provider, project, model, token_class, day = parts
    return (provider, project, model, token_class, day)


def group_by_match_key(items: Iterable[_T], *, key: Callable[[_T], str]) -> dict[str, list[_T]]:
    """Bucket ``items`` by their match key, preserving input order within each bucket.

    Args:
        items: the things to group (cost events, estimate rows, ...).
        key: extracts the match-key string from one item.

    Returns:
        A mapping from match key to the items carrying it, in first-seen order.
    """
    grouped: dict[str, list[_T]] = defaultdict(list)
    for item in items:
        grouped[key(item)].append(item)
    return dict(grouped)


__all__ = ["group_by_match_key", "match_key_of", "parse_match_key"]
