"""Entity aliasing — re-joining traffic that was anonymous when it happened.

The hole this closes: a session starts unknown (`session_id=abc`), spends real money
answering questions, and only later becomes a known lead (`lead_id=8172`). Every span
captured before that moment carries the anonymous key. Without an alias they are
permanently orphaned — the spend is real, the outcome is real, and nothing joins them.

Aliases are resolved at QUERY time rather than by rewriting stored spans. Two reasons,
both load-bearing:

- History stays honest. A span recorded what the caller actually sent; editing it later
  would make the record disagree with what happened.
- Aliases arrive late by nature. A rewrite-on-write scheme has to be replayed for every
  alias, forever, and silently misses anything already aggregated.

The relation is symmetric and transitive: `a→b` and `b→c` means a query for any one of
them must consider all three. Callers state one edge; the closure is ours to compute.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

EntityKey = tuple[str, str]


@dataclass(frozen=True, slots=True)
class EntityAlias:
    """One asserted identity edge between two entity keys.

    `source` is the key that was used at capture time (typically the anonymous one)
    and `target` is what it turned out to be. The direction is recorded because it is
    useful to a human reading the audit trail, but resolution treats the pair as
    symmetric — an identity claim does not have a direction.
    """

    source: EntityKey
    target: EntityKey


def resolve_aliases(key: EntityKey, aliases: Iterable[EntityAlias]) -> frozenset[EntityKey]:
    """Every entity key that is the same entity as `key`, including `key` itself.

    Walks the transitive closure, so a session aliased to a lead that was later merged
    into an account resolves all three. Cycles are terminated by the visited set: a
    caller can assert `a→b` and `b→a` without hanging the query.
    """
    adjacency = _adjacency(aliases)
    seen: set[EntityKey] = {key}
    frontier = [key]
    while frontier:
        current = frontier.pop()
        for neighbour in adjacency.get(current, ()):
            if neighbour in seen:
                continue
            seen.add(neighbour)
            frontier.append(neighbour)
    return frozenset(seen)


def _adjacency(aliases: Iterable[EntityAlias]) -> Mapping[EntityKey, Sequence[EntityKey]]:
    """Undirected adjacency over the asserted edges."""
    out: dict[EntityKey, list[EntityKey]] = {}
    for alias in aliases:
        out.setdefault(alias.source, []).append(alias.target)
        out.setdefault(alias.target, []).append(alias.source)
    return out


__all__ = ["EntityAlias", "EntityKey", "resolve_aliases"]
