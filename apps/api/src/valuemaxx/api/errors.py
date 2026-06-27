"""Typed errors for the API surface (mapped to HTTP status codes by the app)."""

from __future__ import annotations


class ApiError(Exception):
    """Base class for every API-surface error."""


class AuthError(ApiError):
    """The request could not be authenticated (no/unknown API key) -> 401."""


class WebhookSignatureError(ApiError):
    """A webhook body failed signature verification -> 401 (handler not called)."""


class JobNotFoundError(ApiError):
    """A polled async job id is unknown -> 404."""


__all__ = ["ApiError", "AuthError", "JobNotFoundError", "WebhookSignatureError"]
