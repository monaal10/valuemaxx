"""``python -m valuemaxx.server`` — serve the assembly app with uvicorn.

Reads :class:`~valuemaxx.server.settings.ServerSettings` from the environment for
the bind host/port, then serves ``valuemaxx.server.app:app`` (the store opens, and
migrations run, on ASGI startup). Equivalent to
``uvicorn valuemaxx.server.app:app --host $VALUEMAXX_HOST --port $VALUEMAXX_PORT``.
"""

from __future__ import annotations

import uvicorn
from valuemaxx.server.settings import DEV_INGEST_KEY, ServerSettings


def main() -> None:
    """Serve the assembly app with uvicorn using the env-configured host/port."""
    settings = ServerSettings()
    if settings.is_using_dev_fallback():
        # Zero-config (e.g. `docker run valuemaxx-backend` with no env): surface the
        # synthesized dev key in the startup logs so a user knows how to authenticate —
        # the container has no other way to tell them. Mirrors the CLI `up` hint.
        print(
            f'valuemaxx: no ingest key configured — using dev key "{DEV_INGEST_KEY}" '
            f'(send header "X-API-Key: {DEV_INGEST_KEY}"). '
            f"Set VALUEMAXX_INGEST_KEYS for your own keys.",
            flush=True,
        )
    uvicorn.run(
        "valuemaxx.server.app:app",
        host=settings.host,
        port=settings.port,
    )


if __name__ == "__main__":  # pragma: no cover - process entrypoint
    main()
