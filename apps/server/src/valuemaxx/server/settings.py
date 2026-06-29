"""Server settings — env-driven configuration for the runnable assembly (§5b).

:class:`ServerSettings` reads the deployment configuration from the environment (a
``.env`` file is honored) via pydantic-settings: the storage URL, the ingest
key->tenant map, the bind host/port, the webhook HMAC secret, and the content-
capture flag. Defaults boot a local SQLite store so ``create_app()`` runs with no
configuration; production overrides ``VALUEMAXX_DATABASE_URL`` (Postgres) and the
ingest keys via the environment.

The ingest keys map each ``X-API-Key`` to its tenant **UUID string** (tenancy is
identified by UUID, §3.2). The API-key authenticator resolves the tenant from the
key — never from the request body — so a caller can only ever act on its own
tenant. Secrets (the webhook secret, the ingest keys) come from the env/secret
store and are never committed (AGENTS.md §5).
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Zero-config local dev: when no ingest key is configured, the backend synthesizes this
# stable key -> tenant so the first run "just works". Both are FIXED (not random) so a
# restart reuses the same tenant and data persisted under it stays readable — never
# orphaned under a fresh random tenant. Configuring real keys turns this fallback off.
DEV_INGEST_KEY = "dev"
DEV_TENANT_ID = "00000000-0000-4000-8000-000000000001"


class ServerSettings(BaseSettings):
    """Environment-driven configuration for :func:`~valuemaxx.server.app.create_app`.

    Every field is overridable via a ``VALUEMAXX_``-prefixed environment variable
    (e.g. ``VALUEMAXX_DATABASE_URL``). ``ingest_keys`` is a JSON object mapping an
    ingest/API key to its tenant UUID string.
    """

    model_config = SettingsConfigDict(
        env_prefix="VALUEMAXX_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(
        default="sqlite+aiosqlite:///./valuemaxx.db",
        description="SQLAlchemy async URL; Postgres in prod (postgresql+asyncpg://...).",
    )
    ingest_keys: dict[str, str] = Field(
        default_factory=dict,
        description="Ingest/API key -> tenant UUID string. Resolves the tenant per request.",
    )
    webhook_secret: str = Field(
        default="dev-webhook-secret",
        description="HMAC secret used to verify webhook_inbound (OTLP ingest) bodies.",
    )
    host: str = Field(default="127.0.0.1", description="The bind host for the ASGI server.")
    port: int = Field(default=8000, description="The bind port for the ASGI server.")
    capture_content: bool = Field(
        default=False,
        description="Whether to capture prompt/completion content (off by default; PII).",
    )

    def webhook_secret_bytes(self) -> bytes:
        """The webhook secret as bytes (the signature verifier takes bytes)."""
        return self.webhook_secret.encode("utf-8")

    def is_using_dev_fallback(self) -> bool:
        """True iff no ingest key is configured, so the dev key->tenant is synthesized."""
        return not self.ingest_keys

    def resolved_ingest_keys(self) -> dict[str, str]:
        """The effective ingest-key -> tenant map the app authenticates against.

        Returns the configured ``ingest_keys`` as-is, or — when none are configured — a
        single deterministic dev key (:data:`DEV_INGEST_KEY` -> :data:`DEV_TENANT_ID`) so
        ``valuemaxx up`` is usable zero-config. There is still NO anonymous tenant: every
        request resolves a tenant from a key; the dev fallback just supplies a known one.
        """
        if self.ingest_keys:
            return dict(self.ingest_keys)
        return {DEV_INGEST_KEY: DEV_TENANT_ID}


__all__ = ["DEV_INGEST_KEY", "DEV_TENANT_ID", "ServerSettings"]
