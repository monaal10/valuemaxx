"""Secret-safe logging helpers (the no_secret_logging guardrail surface)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from valuemaxx.outcomes.safelog import get_logger, redact_secrets

if TYPE_CHECKING:
    import pytest


def test_redact_known_secret_kinds() -> None:
    """API-key-shaped and ingest-key-shaped tokens are redacted from a message."""
    msg = "verifying key sk-ant-SUPERSECRET-1234 and ingest whsec_ABCDEF0123456789"
    cleaned = redact_secrets(msg)
    assert "sk-ant-SUPERSECRET-1234" not in cleaned
    assert "whsec_ABCDEF0123456789" not in cleaned
    assert "[REDACTED]" in cleaned


def test_redact_passes_through_innocuous_text() -> None:
    """Ordinary text is left untouched."""
    assert redact_secrets("processed outcome loan_funded for run-42") == (
        "processed outcome loan_funded for run-42"
    )


def test_logger_redacts_secrets_in_emitted_records(caplog: pytest.LogCaptureFixture) -> None:
    """A logger from get_logger redacts secrets before they reach a handler."""
    logger = get_logger("valuemaxx.outcomes.test")
    with caplog.at_level(logging.WARNING, logger="valuemaxx.outcomes.test"):
        logger.warning("leaking sk-ant-NOPE-0xDEADBEEF into the log")
    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert "sk-ant-NOPE-0xDEADBEEF" not in joined
    assert "[REDACTED]" in joined


def test_get_logger_is_idempotent() -> None:
    """Re-fetching the same logger does not stack duplicate redaction filters."""
    a = get_logger("valuemaxx.outcomes.dup")
    b = get_logger("valuemaxx.outcomes.dup")
    assert a is b
    assert len(a.filters) == 1
