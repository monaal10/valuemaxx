"""Tests for secret detection + redaction (FOUNDATION).

Secrets encountered during a scan must NEVER reach a proposal field, a diff, or a
log (design §7 / H12). ``redact`` is the mechanical guarantee: every captured
string passes through it before it leaves the scanner.
"""

from __future__ import annotations

import pytest

from valuemaxx.onboarding.errors import SecretEncounteredError
from valuemaxx.onboarding.redact import (
    REDACTION_PLACEHOLDER,
    assert_no_secret,
    contains_secret,
    redact,
)

_ANTHROPIC = "sk-ant-api03-" + "A1b2C3d4E5" * 5
_ANTHROPIC_ADMIN = "sk-ant-admin01-" + "Z9y8X7w6V5" * 5
_OPENAI = "sk-" + "proj0011AbCdEfGh" * 3
_AWS_AKIA = "AKIAIOSFODNN7EXAMPLE"
_BEARER = "Bearer abcdef0123456789abcdef0123456789"


@pytest.mark.parametrize(
    "secret",
    [_ANTHROPIC, _ANTHROPIC_ADMIN, _OPENAI, _AWS_AKIA, _BEARER],
    ids=["anthropic", "anthropic-admin", "openai", "aws-akia", "bearer"],
)
def test_contains_secret_detects_known_key_shapes(secret: str) -> None:
    assert contains_secret(secret) is True
    assert contains_secret(f"the key is {secret} ok") is True


def test_contains_secret_detects_assignment_form() -> None:
    assert contains_secret('API_KEY = "hunter2-super-secret-value-9999"') is True
    assert contains_secret("password='p@ssw0rd-not-in-diff-please-1234'") is True
    assert contains_secret("auth_token: shhhh-this-is-a-token-value-7777") is True


def test_contains_secret_detects_high_entropy_blob() -> None:
    # a long mixed-case+digit run with no spaces — looks like a credential
    assert contains_secret("dGhpcyBpcyBhIHZlcnkgbG9uZyBoaWdoIGVudHJvcHkgYmxvYjEyMzQ1") is True


def test_clean_text_is_not_flagged() -> None:
    for clean in (
        "def mark_resolved(ticket): ticket.status = 'resolved'",
        "run_id = correlation_id",
        "the quick brown fox jumps over the lazy dog",
        "status_code == 200 and amount > 0",
    ):
        assert contains_secret(clean) is False, clean


def test_redact_replaces_secret_with_placeholder() -> None:
    out = redact(f"client = Anthropic(api_key='{_ANTHROPIC}')")
    assert _ANTHROPIC not in out
    assert REDACTION_PLACEHOLDER in out


def test_redact_is_idempotent() -> None:
    once = redact(f"key={_OPENAI}")
    twice = redact(once)
    assert once == twice
    assert _OPENAI not in once


def test_redact_leaves_clean_text_unchanged() -> None:
    clean = "ticket.status = 'closed'  # outcome site"
    assert redact(clean) == clean


def test_assert_no_secret_raises_on_secret() -> None:
    with pytest.raises(SecretEncounteredError):
        assert_no_secret(f"token {_AWS_AKIA}")


def test_assert_no_secret_passes_clean_text() -> None:
    assert_no_secret("nothing secret here")  # must not raise
