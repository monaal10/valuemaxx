"""Secret detection + redaction — the mechanical "no secret ever leaves" guarantee.

Every string the scanner captures from the user's codebase passes through
:func:`redact` before it can reach a proposal field, a diff hunk, or a log line
(design §7 / H12). Detection is conservative and additive: it anchors on the key
shapes this product encounters (Anthropic/OpenAI ``sk-`` keys, Anthropic admin
keys, AWS ``AKIA`` access-key ids, ``Bearer`` tokens), plus an assignment-form
heuristic (``API_KEY = "..."``) and a high-entropy-blob heuristic for credentials
that carry no recognisable prefix.

:func:`contains_secret` answers "is there a secret-shaped token here?";
:func:`redact` replaces every such token with :data:`REDACTION_PLACEHOLDER` and is
idempotent; :func:`assert_no_secret` raises :class:`SecretEncounteredError` when a
string that must be secret-free is not — it is the last gate before any output.
"""

from __future__ import annotations

import math
import re
from typing import Final

from valuemaxx.onboarding import rules
from valuemaxx.onboarding.errors import SecretEncounteredError

# Redaction constants come from the single-source ``rules`` module (serialized to the
# cross-language fixture the TS redactor reads), so Python + TS scrub the same shapes.
REDACTION_PLACEHOLDER: Final[str] = rules.REDACTION_PLACEHOLDER

# Prefixed key shapes. Anchored on known prefixes so ordinary identifiers (run
# ids, outcome names, status strings) are never scrubbed by accident. The admin
# pattern is listed first so it wins over the generic ``sk-ant`` pattern.
_PREFIX_PATTERNS: Final[tuple[re.Pattern[str], ...]] = tuple(
    re.compile(p) for p in rules.REDACT_PREFIX_PATTERNS
)

# Assignment form: a secret-named identifier set to a non-trivial value, e.g.
# ``API_KEY = "..."`` / ``password='...'`` / ``auth_token: ...``. Captures the
# value side (group ``val``) so we redact the secret, not the whole assignment.
_ASSIGNMENT_PATTERN: Final[re.Pattern[str]] = re.compile(
    rf"(?i)\b(?:{rules.REDACT_SECRET_NAME_ALT})\b\s*[:=]\s*"
    rf"(?P<val>(?:\"[^\"]{{6,}}\"|'[^']{{6,}}'|[^\s'\"]{{6,}}))",
)

# A long unbroken run of base64/credential-ish characters with no whitespace.
# Real prose and code break into short whitespace-separated tokens, so this fires
# only on credential-like blobs.
_HIGH_ENTROPY_TOKEN: Final[re.Pattern[str]] = re.compile(rules.REDACT_HIGH_ENTROPY_PATTERN)
_HIGH_ENTROPY_BITS: Final[float] = rules.REDACT_HIGH_ENTROPY_BITS


def _shannon_entropy(token: str) -> float:
    """Bits-per-character Shannon entropy of ``token`` (0.0 for an empty string)."""
    if not token:
        return 0.0
    counts: dict[str, int] = {}
    for char in token:
        counts[char] = counts.get(char, 0) + 1
    length = len(token)
    return -sum((c / length) * math.log2(c / length) for c in counts.values())


def _is_high_entropy_secret(token: str) -> bool:
    """True iff ``token`` is a long, high-entropy, multi-class credential blob."""
    if len(token) < 40:
        return False
    has_upper = any(c.isupper() for c in token)
    has_lower = any(c.islower() for c in token)
    has_digit = any(c.isdigit() for c in token)
    # Require mixed character classes — a long lowercase word is not a credential.
    if not (has_upper and has_lower and has_digit):
        return False
    return _shannon_entropy(token) >= _HIGH_ENTROPY_BITS


def _high_entropy_spans(text: str) -> list[tuple[int, int]]:
    """The (start, end) spans of high-entropy credential blobs in ``text``."""
    return [
        m.span() for m in _HIGH_ENTROPY_TOKEN.finditer(text) if _is_high_entropy_secret(m.group(0))
    ]


def contains_secret(text: str) -> bool:
    """Return True iff ``text`` contains a secret-shaped token."""
    if any(pattern.search(text) for pattern in _PREFIX_PATTERNS):
        return True
    if _ASSIGNMENT_PATTERN.search(text):
        return True
    return bool(_high_entropy_spans(text))


def redact(text: str) -> str:
    """Return ``text`` with every secret-shaped token replaced by the placeholder.

    Idempotent: redacting already-redacted text is a no-op (the placeholder is not
    itself secret-shaped). Clean text is returned unchanged.
    """
    cleaned = text
    for pattern in _PREFIX_PATTERNS:
        cleaned = pattern.sub(REDACTION_PLACEHOLDER, cleaned)
    cleaned = _ASSIGNMENT_PATTERN.sub(
        lambda m: m.group(0).replace(m.group("val"), REDACTION_PLACEHOLDER), cleaned
    )
    # High-entropy blobs: redact right-to-left so earlier spans keep their offsets.
    for start, end in reversed(_high_entropy_spans(cleaned)):
        cleaned = cleaned[:start] + REDACTION_PLACEHOLDER + cleaned[end:]
    return cleaned


def assert_no_secret(text: str) -> None:
    """Raise :class:`SecretEncounteredError` if ``text`` still contains a secret.

    This is the final gate before a string is written to a proposal/diff/PR/log.
    Callers that can recover should :func:`redact` first; this asserts the invariant.
    """
    if contains_secret(text):
        raise SecretEncounteredError(
            "a secret-shaped token reached an output that must never carry a secret"
        )


__all__ = [
    "REDACTION_PLACEHOLDER",
    "assert_no_secret",
    "contains_secret",
    "redact",
]
