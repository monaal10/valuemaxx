"""Drain-style prompt templatization — hash the SKELETON, never the filled string.

§8.1 templatizes the residue of the deterministic group-by backbone with Drain:
two prompts that differ only in their filled-in literals (ids, numbers, emails,
urls, quoted values) belong to the same agent/prompt cluster, so we mask those
literals to wildcards and hash the resulting *skeleton*. Hashing the filled string
would explode one logical prompt into thousands of singletons.

The masking is deterministic and content-addressable (sha256 of the skeleton), so
the same skeleton always yields the same cluster id across runs — never Python's
per-process salted ``hash()``.
"""

from __future__ import annotations

import hashlib
import re

# Order matters: mask the most specific high-cardinality literals first (urls and
# emails contain digits we do not want the bare-number rule to half-mask), then
# generic numbers, then quoted values.
_URL = re.compile(r"https?://\S+")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_HEXID = re.compile(r"\b[0-9a-fA-F]{8,}\b")
_NUMBER = re.compile(r"#?\b\d+(?:\.\d+)?\b")
_QUOTED = re.compile(r'"[^"]*"|\'[^\']*\'')
_WS = re.compile(r"\s+")


def templatize(prompt: str) -> str:
    """Return the prompt SKELETON with high-cardinality literals masked to wildcards.

    Masks urls, emails, hex ids, numbers, and quoted values, collapsing whitespace.
    Structural (non-literal) tokens survive, so the skeleton keeps the prompt's
    shape while erasing the values that vary call to call.
    """
    out = _URL.sub("<URL>", prompt)
    out = _EMAIL.sub("<EMAIL>", out)
    out = _HEXID.sub("<HEX>", out)
    out = _QUOTED.sub("<STR>", out)
    out = _NUMBER.sub("<NUM>", out)
    return _WS.sub(" ", out).strip()


def skeleton_hash(prompt: str) -> str:
    """Return the stable sha256 hex digest of the prompt's skeleton (§8.1).

    Content-addressable and deterministic across processes (unlike ``hash()``),
    so two prompts that differ only in literals share a cluster id forever.
    """
    return hashlib.sha256(templatize(prompt).encode("utf-8")).hexdigest()


__all__ = ["skeleton_hash", "templatize"]
