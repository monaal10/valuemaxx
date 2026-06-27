"""Shared helpers for the CLI app tests (package-unique, bare-imported §5b).

A precisely-typed view over the starlette ``TestClient`` whose ``post``/``get``
reference httpx private aliases pyright cannot resolve. The ``up`` smoke test boots
the real assembly app and hits a mounted route to prove the projection responds
(auth/validation), so it needs a typed ``post`` return. Imported via a bare
``from _cli_helpers import ...`` — never ``from tests...`` (which collides repo-wide
under ``--import-mode=importlib``; AGENTS.md §5b).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, cast

if TYPE_CHECKING:
    import httpx
    from fastapi.testclient import TestClient


class _HttpClient(Protocol):
    """A precisely-typed view of the (otherwise pyright-opaque) starlette TestClient."""

    def post(
        self,
        url: str,
        *,
        json: object | None = ...,
        content: bytes | None = ...,
        headers: dict[str, str] | None = ...,
    ) -> httpx.Response: ...

    def get(self, url: str, *, headers: dict[str, str] | None = ...) -> httpx.Response: ...


def post_json(client: TestClient, url: str, body: dict[str, object]) -> httpx.Response:
    """POST ``body`` as JSON via the TestClient, returning a precisely-typed response.

    Contains the one ``cast`` over the pyright-opaque TestClient so the tests see a
    concrete ``httpx.Response`` (with a typed ``status_code``).
    """
    return cast("_HttpClient", client).post(url, json=body)


def route_paths(app: object) -> set[str]:
    """The mounted route paths of an ASGI app (``app.routes[*].path``), pyright-safe."""
    routes = cast("list[object]", getattr(app, "routes", []))
    return {str(path) for route in routes if (path := getattr(route, "path", None)) is not None}


__all__ = ["post_json", "route_paths"]
