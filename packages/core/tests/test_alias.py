"""Alias resolution — the rule that lets anonymous traffic re-join later."""

from __future__ import annotations

from valuemaxx.core.alias import EntityAlias, resolve_aliases

_SESSION = ("session_id", "abc")
_LEAD = ("lead_id", "8172")
_ACCOUNT = ("account_id", "acme")


def test_a_key_with_no_aliases_resolves_to_itself() -> None:
    assert resolve_aliases(_SESSION, []) == frozenset({_SESSION})


def test_an_alias_is_symmetric() -> None:
    """Querying from either end must find the other.

    The caller states `session → lead` because that is the direction the knowledge
    arrived in, but identity has no direction: cost captured under the session and an
    outcome recorded against the lead are the same entity's, whichever one is asked for.
    """
    aliases = [EntityAlias(source=_SESSION, target=_LEAD)]

    assert resolve_aliases(_SESSION, aliases) == frozenset({_SESSION, _LEAD})
    assert resolve_aliases(_LEAD, aliases) == frozenset({_SESSION, _LEAD})


def test_aliases_are_transitive() -> None:
    """Anonymous session → lead → merged account is one entity, not three."""
    aliases = [
        EntityAlias(source=_SESSION, target=_LEAD),
        EntityAlias(source=_LEAD, target=_ACCOUNT),
    ]

    assert resolve_aliases(_SESSION, aliases) == frozenset({_SESSION, _LEAD, _ACCOUNT})


def test_a_cycle_terminates() -> None:
    """A caller asserting both directions must not hang the query."""
    aliases = [
        EntityAlias(source=_SESSION, target=_LEAD),
        EntityAlias(source=_LEAD, target=_SESSION),
    ]

    assert resolve_aliases(_SESSION, aliases) == frozenset({_SESSION, _LEAD})


def test_unrelated_entities_stay_separate() -> None:
    """Over-resolving would merge two customers' spend — worse than not joining."""
    aliases = [EntityAlias(source=_SESSION, target=_LEAD)]

    assert resolve_aliases(("lead_id", "9999"), aliases) == frozenset({("lead_id", "9999")})
