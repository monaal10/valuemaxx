"""Tenant resolution from the API/ingest key (§4/§11 — tenant from the key, not the body).

Every API route resolves its tenant from the ``X-API-Key`` header via a configured
key->tenant map. The tenant is NEVER trusted from the request body: the resolved
tenant overrides any ``tenant_id`` in the payload, so a caller authenticated as
tenant A can never read or write tenant B's data. A missing or unknown key is an
:class:`~valuemaxx.api.errors.AuthError` (the app maps this to HTTP 401).
"""

from __future__ import annotations

from valuemaxx.api.errors import AuthError


class ApiKeyAuthenticator:
    """Resolves an API key to its tenant via an immutable key->tenant map."""

    def __init__(self, api_keys: dict[str, str]) -> None:
        # Copy so a later mutation of the caller's dict cannot change resolution.
        self._keys: dict[str, str] = dict(api_keys)

    def resolve_tenant(self, api_key: str | None) -> str:
        """Return the tenant for ``api_key``, or raise :class:`AuthError`.

        A ``None`` or empty key, or a key not in the configured map, raises — the
        route maps the error to a 401. There is no anonymous/default tenant.
        """
        if not api_key:
            raise AuthError("missing API key")
        tenant = self._keys.get(api_key)
        if tenant is None:
            raise AuthError("unknown API key")
        return tenant


__all__ = ["ApiKeyAuthenticator"]
