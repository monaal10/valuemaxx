"""API auth tests — the tenant is resolved from the API key, never trusted from the body.

Every API route resolves its tenant from the ``X-API-Key`` header via the configured
key->tenant map. A missing or unknown key is a 401; a known key resolves to exactly
its tenant. The resolved tenant is the only tenant a request may act on.
"""

from __future__ import annotations

import pytest
from valuemaxx.api.auth import ApiKeyAuthenticator
from valuemaxx.api.errors import AuthError


def _auth() -> ApiKeyAuthenticator:
    return ApiKeyAuthenticator({"key-a": "tenant-a", "key-b": "tenant-b"})


def test_known_key_resolves_to_its_tenant() -> None:
    """A configured key resolves to exactly its tenant."""
    auth = _auth()
    assert auth.resolve_tenant("key-a") == "tenant-a"
    assert auth.resolve_tenant("key-b") == "tenant-b"


def test_unknown_key_is_rejected() -> None:
    """An unknown key raises AuthError (the route maps this to 401)."""
    auth = _auth()
    with pytest.raises(AuthError):
        auth.resolve_tenant("key-unknown")


def test_missing_key_is_rejected() -> None:
    """An empty/None key raises AuthError."""
    auth = _auth()
    with pytest.raises(AuthError):
        auth.resolve_tenant(None)
    with pytest.raises(AuthError):
        auth.resolve_tenant("")
