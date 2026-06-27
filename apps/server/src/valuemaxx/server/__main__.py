"""``python -m valuemaxx.server`` — serve the assembly app with uvicorn.

Reads :class:`~valuemaxx.server.settings.ServerSettings` from the environment for
the bind host/port, then serves ``valuemaxx.server.app:app`` (the store opens, and
migrations run, on ASGI startup). Equivalent to
``uvicorn valuemaxx.server.app:app --host $VALUEMAXX_HOST --port $VALUEMAXX_PORT``.
"""

from __future__ import annotations

import uvicorn
from valuemaxx.server.settings import ServerSettings


def main() -> None:
    """Serve the assembly app with uvicorn using the env-configured host/port."""
    settings = ServerSettings()
    uvicorn.run(
        "valuemaxx.server.app:app",
        host=settings.host,
        port=settings.port,
    )


if __name__ == "__main__":  # pragma: no cover - process entrypoint
    main()
