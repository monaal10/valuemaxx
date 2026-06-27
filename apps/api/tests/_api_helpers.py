"""Shared test helpers for the api app (package-unique, bare-imported per §5b).

Provides a tiny tenant-scoped read capability backed by an in-memory store, used to
prove tenant isolation through a real route: a request authenticated as tenant A
must only ever see tenant A's rows, never tenant B's.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, cast

from pydantic import BaseModel
from valuemaxx.capabilities import CapabilitySpec, Mode, Registry, Surface, capability

if TYPE_CHECKING:
    import httpx
    from fastapi.testclient import TestClient


class _HttpClient(Protocol):
    """A precisely-typed view of the (otherwise pyright-opaque) starlette TestClient.

    The starlette ``TestClient`` references httpx private type aliases pyright cannot
    resolve, so its ``post``/``get`` read as Unknown. Casting the client to this
    Protocol gives the tests clean, typed call sites without touching production code.
    """

    def post(
        self,
        url: str,
        *,
        json: object | None = ...,
        content: bytes | None = ...,
        headers: dict[str, str] | None = ...,
    ) -> httpx.Response: ...

    def get(self, url: str, *, headers: dict[str, str] | None = ...) -> httpx.Response: ...


# An in-memory per-tenant store: tenant_id -> list of note strings.
_STORE: dict[str, list[str]] = {
    "tenant-a": ["a-secret-note"],
    "tenant-b": ["b-secret-note"],
}


class ListNotesInput(BaseModel):
    """Request to list the calling tenant's notes (tenant_id is the scope)."""

    tenant_id: str


class ListNotesOutput(BaseModel):
    """The notes visible to the calling tenant (only ever that tenant's rows)."""

    tenant_id: str
    notes: tuple[str, ...]


def _list_notes(request: ListNotesInput) -> ListNotesOutput:
    # The handler reads ONLY the requested tenant's rows — the API layer guarantees
    # the tenant_id equals the authenticated tenant, so cross-tenant reads are
    # impossible through the route.
    notes = tuple(_STORE.get(request.tenant_id, ()))
    return ListNotesOutput(tenant_id=request.tenant_id, notes=notes)


def list_notes_capability() -> CapabilitySpec[ListNotesInput, ListNotesOutput]:
    """A tenant-scoped read capability for the isolation tests."""
    return capability(
        name="list_notes",
        input_model=ListNotesInput,
        output_model=ListNotesOutput,
        handler=_list_notes,
        description="List the calling tenant's notes (tenant-scoped read).",
        surfaces=Surface.API | Surface.MCP | Surface.CLI,
        mode=Mode.REQUEST_RESPONSE,
    )


def registry_with_notes() -> Registry:
    """A registry containing just the tenant-scoped notes read capability."""
    registry = Registry()
    registry.register(list_notes_capability())
    return registry


# Typed thin wrappers over the (untyped-to-pyright) starlette TestClient. The
# TestClient's post/get reference httpx private type aliases pyright cannot resolve,
# so it treats their returns as Unknown; we contain that in one cast and expose a
# precise httpx.Response to the tests.


def post(
    client: TestClient,
    path: str,
    *,
    json: object | None = None,
    content: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    """POST via the TestClient, returning a typed ``httpx.Response``.

    The starlette TestClient is opaque to pyright (httpx private aliases), so we view
    it through the typed :class:`_HttpClient` Protocol — containing the unknown in one
    cast.
    """
    return cast("_HttpClient", client).post(path, json=json, content=content, headers=headers)


def get(client: TestClient, path: str, *, headers: dict[str, str] | None = None) -> httpx.Response:
    """GET via the TestClient, returning a typed ``httpx.Response`` (see :func:`post`)."""
    return cast("_HttpClient", client).get(path, headers=headers)


def route_paths(app: object) -> set[str]:
    """The set of mounted route paths on a FastAPI app (typed access)."""
    routes = cast("list[object]", getattr(app, "routes", []))
    paths: set[str] = set()
    for route in routes:
        path = getattr(route, "path", None)
        if isinstance(path, str):
            paths.add(path)
    return paths
