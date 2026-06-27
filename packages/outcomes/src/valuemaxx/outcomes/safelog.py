"""Secret-safe logging (the ``no_secret_logging`` guardrail, AGENTS.md §5b).

Provider keys and webhook ingest/signing secrets must **never** reach a log line, a
span attribute, or a DB row. This module provides:

* :func:`redact_secrets` — replace any secret-shaped token in a string with
  ``[REDACTED]`` (defence in depth; the primary defence is never passing a secret to
  a logger in the first place).
* :func:`get_logger` — a logger with a redaction :class:`logging.Filter` attached, so
  even an accidental secret in a log call is scrubbed before any handler sees it.

The patterns cover the key shapes this product handles (Anthropic/OpenAI ``sk-`` keys
and Stripe-style ``whsec_`` webhook secrets); the filter is conservative and additive.
"""

from __future__ import annotations

import logging
import re
from typing import Final

from typing_extensions import override  # py3.11 target: typing.override is 3.12+

_REDACTED: Final[str] = "[REDACTED]"

# Secret-shaped tokens. Conservative, anchored on known prefixes so we never scrub
# ordinary identifiers (run ids, outcome names) by accident.
_SECRET_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"sk-[A-Za-z0-9-]{8,}"),  # OpenAI / Anthropic-style API keys
    re.compile(r"whsec_[A-Za-z0-9]{8,}"),  # Stripe-style webhook signing secrets
    re.compile(r"ingest_[A-Za-z0-9]{8,}"),  # our ingest keys
)


def redact_secrets(message: str) -> str:
    """Return ``message`` with any secret-shaped token replaced by ``[REDACTED]``."""
    cleaned = message
    for pattern in _SECRET_PATTERNS:
        cleaned = pattern.sub(_REDACTED, cleaned)
    return cleaned


class _RedactionFilter(logging.Filter):
    """A logging filter that scrubs secret-shaped tokens from every record's message."""

    @override
    def filter(self, record: logging.LogRecord) -> bool:
        """Rewrite the record's message in place; always returns True (never drops)."""
        # getMessage() applies args; we redact the final rendered text and freeze it.
        record.msg = redact_secrets(record.getMessage())
        record.args = None
        return True


def get_logger(name: str) -> logging.Logger:
    """Return a logger that redacts secrets, attaching the filter at most once."""
    logger = logging.getLogger(name)
    if not any(isinstance(f, _RedactionFilter) for f in logger.filters):
        logger.addFilter(_RedactionFilter())
    return logger


__all__ = ["get_logger", "redact_secrets"]
