"""T2 inbound: parse a raw W3C ``baggage`` header into the cascade's baggage map.

The receiving service's ingress calls :func:`parse_baggage_header` on the inbound
``baggage`` header to recover the ``Mapping[str, str]`` the
:class:`~valuemaxx.attribution.binding.t2_baggage.BaggageResolver` reads. This is the
inbound sibling of the SDK's baggage producer; the two agree on the W3C list encoding
(``key=value`` members joined by ``,``).

Pure + total: malformed members (no ``=``, empty key) are skipped rather than raised, so a
mangled header degrades to fewer members instead of failing the bind. It never invents a
run id — an absent/blank header yields an empty map and the cascade simply falls through.
"""

from __future__ import annotations


def parse_baggage_header(raw: str | None) -> dict[str, str]:
    """Parse a W3C ``baggage`` header value into a ``{key: value}`` map.

    Members are comma-separated ``key=value`` pairs; optional whitespace (OWS) around a
    member is trimmed. A member without a ``=`` or with an empty key is skipped. Returns
    an empty map for ``None`` / blank input.
    """
    if raw is None or not raw.strip():
        return {}
    parsed: dict[str, str] = {}
    for member in raw.split(","):
        trimmed = member.strip()
        if "=" not in trimmed:
            continue
        key, _, value = trimmed.partition("=")
        key = key.strip()
        if not key:
            continue
        parsed[key] = value.strip()
    return parsed


__all__ = ["parse_baggage_header"]
