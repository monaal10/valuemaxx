"""tenant_guard — every read is scoped by tenant_id, structurally (§3.2).

``require_tenant`` is the single chokepoint repositories route every ``select``
through, so an AST conformance scan can prove no query path omits the tenant scope.
It appends ``WHERE table.c.tenant_id == tenant_id`` to the statement and returns it.
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select
from valuemaxx.core.ids import TenantId
from valuemaxx.store.tables import run
from valuemaxx.store.tenant_guard import require_tenant


def test_require_tenant_appends_where_clause() -> None:
    """require_tenant adds a tenant_id equality predicate to the statement."""
    tenant = TenantId(uuid4())
    stmt = require_tenant(select(run), tenant, run)
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": False}))
    assert "tenant_id" in compiled
    assert "WHERE" in compiled.upper()


def test_require_tenant_binds_the_given_tenant() -> None:
    """The bound parameter carries exactly the supplied tenant id."""
    tenant = TenantId(uuid4())
    stmt = require_tenant(select(run), tenant, run)
    params = stmt.compile().params
    assert tenant in params.values()
