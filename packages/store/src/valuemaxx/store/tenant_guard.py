"""The tenant-scope chokepoint — every read filters on tenant_id (§3.2).

There is no API to query the store without a tenant scope: every repository routes
its ``select`` through :func:`require_tenant`, which appends a
``WHERE table.c.tenant_id == tenant_id`` predicate. Routing through one named
function (rather than inlining ``.where(...)`` at each call site) is what lets the
``tenant_scoping`` conformance scan prove, by AST, that no read path omits the scope
— isolation is structural, not disciplinary.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from sqlalchemy import Select, Table
    from valuemaxx.core.ids import TenantId

_T = TypeVar("_T", bound="tuple[object, ...]")


def require_tenant(stmt: Select[_T], tenant_id: TenantId, table: Table) -> Select[_T]:
    """Scope a SELECT to one tenant by appending ``WHERE table.tenant_id == tenant_id``.

    Args:
        stmt: the select being built.
        tenant_id: the mandatory tenant scope (no query runs without it).
        table: the table whose ``tenant_id`` column is filtered.

    Returns:
        The statement with the tenant predicate appended.
    """
    return stmt.where(table.c.tenant_id == tenant_id)


__all__ = ["require_tenant"]
