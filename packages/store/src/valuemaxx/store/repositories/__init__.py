"""Concrete async SQLAlchemy repositories — one per core repository ABC.

Each ``Pg*Repository`` implements the matching ABC from ``valuemaxx.core``
(``RunRepository``, ``CostEventRepository``, ...), is tenant-scoped through
``tenant_guard.require_tenant``, and is constructed from an ``async_sessionmaker``.
"""

from __future__ import annotations

from valuemaxx.store.repositories.run import PgRunRepository

__all__ = ["PgRunRepository"]
