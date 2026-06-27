"""Webhook signature verification — verify the RAW body BEFORE parsing (§4/§11).

An inbound ``webhook_inbound`` capability is a signed receiver: the route reads the
raw request bytes, verifies an HMAC-SHA256 signature over those exact bytes with a
constant-time compare, and only THEN parses + dispatches. Verifying before parse is
load-bearing — a reserialized-JSON signature would not match the raw bytes, so a
tampered or re-encoded body is rejected (401) and the handler is never called.
"""

from __future__ import annotations

import hashlib
import hmac

from valuemaxx.api.errors import WebhookSignatureError


def verify_signature(secret: bytes, raw_body: bytes, signature: str) -> None:
    """Verify ``signature`` is HMAC-SHA256(``secret``, ``raw_body``); raise otherwise.

    Uses a constant-time comparison (``hmac.compare_digest``) so verification does
    not leak timing. Raises :class:`WebhookSignatureError` (mapped to 401) on any
    mismatch or malformed signature; the caller must not parse the body first.
    """
    expected = hmac.new(secret, raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature or ""):
        raise WebhookSignatureError("webhook signature verification failed")


__all__ = ["verify_signature"]
