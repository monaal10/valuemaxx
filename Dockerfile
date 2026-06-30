# The valuemaxx backend — one language-agnostic image so TS (and any) users run the
# backend without touching Python/pip. It serves the same FastAPI app `valuemaxx up`
# runs: the OTLP collector (POST /v1/traces), the MCP URL (POST /mcp), and the query API.
#
#   docker build -t valuemaxx-backend .
#   docker run -p 8000:8000 valuemaxx-backend
#   # then point your SDK's endpoint at http://localhost:8000
#
# Config is all VALUEMAXX_-env-driven (override with `-e`): VALUEMAXX_INGEST_KEYS (JSON
# key->tenant; omit for the zero-config `dev` key), VALUEMAXX_DATABASE_URL (SQLite by
# default; point at postgresql+asyncpg://… for a persistent multi-process store), etc.

# ---- stage 1: build the single bundled `valuemaxx` wheel from the workspace ----------
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS build

WORKDIR /src
# Copy the whole workspace (the wheel force-includes every valuemaxx.* module from its
# sibling package src dirs; see scripts/bundle_for_release.py).
COPY . .

# Inject the release-only bundle config, then build the wheel into /dist. This is the
# SAME path the release workflow publishes, so the image ships exactly the published
# artifact.
RUN uv run python scripts/bundle_for_release.py \
    && uv build --wheel --package valuemaxx -o /dist

# ---- stage 2: slim runtime with only the backend deps installed ----------------------
FROM python:3.12-slim-bookworm AS runtime

# Non-root runtime user (never run the server as root).
RUN useradd --create-home --uid 10001 valuemaxx
WORKDIR /home/valuemaxx

# Install the bundled wheel with the [server] extra (fastapi/uvicorn/sqlalchemy/asyncpg/
# aiosqlite/… — NOT typer; this is the headless backend, not the CLI).
COPY --from=build /dist/*.whl /tmp/
RUN pip install --no-cache-dir "$(ls /tmp/valuemaxx-*.whl)[server]" && rm -rf /tmp/*.whl

USER valuemaxx

# Bind to 0.0.0.0 inside the container (the default 127.0.0.1 is unreachable from the
# host); the port stays the configurable default. A mounted volume at ./data persists
# the embedded SQLite db across container restarts.
ENV VALUEMAXX_HOST=0.0.0.0 \
    VALUEMAXX_PORT=8000 \
    VALUEMAXX_DATABASE_URL=sqlite+aiosqlite:////home/valuemaxx/data/valuemaxx.db
RUN mkdir -p /home/valuemaxx/data
VOLUME ["/home/valuemaxx/data"]
EXPOSE 8000

# `python -m valuemaxx.server` reads host/port from the env and serves the assembly app
# (store opens + migrations run on ASGI startup).
CMD ["python", "-m", "valuemaxx.server"]
