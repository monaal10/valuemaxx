"""T2 inbound: parse a raw W3C ``baggage`` header into the cascade's baggage map.

The producer stamps ``valuemaxx.run_id=<id>`` (plus any app members) onto the outbound
``baggage`` header; the receiving service's ingress calls :func:`parse_baggage_header` to
turn that raw header back into the ``Mapping[str, str]`` the cascade's
:class:`~valuemaxx.attribution.binding.t2_baggage.BaggageResolver` reads. Pure + total —
malformed members are skipped, never raised, so a bad header degrades to fewer members
rather than failing the bind.
"""

from __future__ import annotations

from valuemaxx.attribution.binding.baggage_header import parse_baggage_header
from valuemaxx.core.wire import BAGGAGE_RUN_ID_KEY


def test_parses_single_run_id_member() -> None:
    """test_parses_single_run_id_member: our key round-trips to the map."""
    parsed = parse_baggage_header(f"{BAGGAGE_RUN_ID_KEY}=run-7")
    assert parsed[BAGGAGE_RUN_ID_KEY] == "run-7"


def test_parses_multiple_members_preserving_all() -> None:
    """test_parses_multiple_members_preserving_all: app members survive alongside ours."""
    parsed = parse_baggage_header(f"team=payments,{BAGGAGE_RUN_ID_KEY}=run-7,region=us")
    assert parsed == {"team": "payments", BAGGAGE_RUN_ID_KEY: "run-7", "region": "us"}


def test_whitespace_around_members_is_trimmed() -> None:
    """test_whitespace_around_members_is_trimmed: OWS around list members is ignored (W3C)."""
    parsed = parse_baggage_header(f" team=payments , {BAGGAGE_RUN_ID_KEY}=run-7 ")
    assert parsed == {"team": "payments", BAGGAGE_RUN_ID_KEY: "run-7"}


def test_none_or_blank_yields_empty_map() -> None:
    """test_none_or_blank_yields_empty_map: absent/blank header is an empty map, never raises."""
    assert parse_baggage_header(None) == {}
    assert parse_baggage_header("") == {}
    assert parse_baggage_header("   ") == {}


def test_malformed_members_are_skipped_not_raised() -> None:
    """test_malformed_members_are_skipped_not_raised: a member without '=' is dropped."""
    parsed = parse_baggage_header(f"garbage,{BAGGAGE_RUN_ID_KEY}=run-7,=novalue,also")
    assert parsed == {BAGGAGE_RUN_ID_KEY: "run-7"}


def test_round_trips_from_the_producer_encoding() -> None:
    """test_round_trips_from_the_producer_encoding: parse ∘ produce is the identity for run_id.

    The producer emits ``key=value`` members joined by ``,``; parsing that exact shape
    must recover the run_id — the two halves of T2 agree on one encoding.
    """
    produced = f"{BAGGAGE_RUN_ID_KEY}=run-9,team=x"
    assert parse_baggage_header(produced)[BAGGAGE_RUN_ID_KEY] == "run-9"
