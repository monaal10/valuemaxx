"""Shared unit-test helpers, imported bare (`from _store_helpers import ...`) to avoid
the cross-package `tests` namespace collision under importlib mode. See AGENTS.md §5b."""

from uuid import uuid4

from valuemaxx.core.ids import TenantId


def make_tenant() -> TenantId:
    """A fresh random tenant id for isolation tests."""
    return TenantId(uuid4())
