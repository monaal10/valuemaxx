"""valuemaxx.store — the persistence layer and migration owner (§9).

Concrete async SQLAlchemy 2.x repositories implementing every ``valuemaxx.core``
repository ABC, behind a configurable storage port (Postgres in production, SQLite for
the driver-agnostic unit path). The store owns all table schema (``tables``) and all
alembic migrations: ``alembic upgrade head`` then ``--autogenerate`` yields an empty
diff. Tenant scope is structural (every read routes through ``tenant_guard``);
reconciliation is append-only; raw JSONB payloads round-trip unmodified for replay;
upserts are idempotent on the per-model idempotency key.
"""

from __future__ import annotations

from valuemaxx.store.capabilities import register
from valuemaxx.store.engine import create_engine, create_sessionmaker
from valuemaxx.store.repositories import (
    PgAllocationRepository,
    PgAttributionResultRepository,
    PgCostEventRepository,
    PgEvalDatasetRepository,
    PgEvalRecommendationRepository,
    PgOutcomeEventRepository,
    PgRawRecordRepository,
    PgReconciliationRepository,
    PgReviewQueue,
    PgRunRepository,
)
from valuemaxx.store.tenant_guard import require_tenant

__all__ = [
    "PgAllocationRepository",
    "PgAttributionResultRepository",
    "PgCostEventRepository",
    "PgEvalDatasetRepository",
    "PgEvalRecommendationRepository",
    "PgOutcomeEventRepository",
    "PgRawRecordRepository",
    "PgReconciliationRepository",
    "PgReviewQueue",
    "PgRunRepository",
    "create_engine",
    "create_sessionmaker",
    "register",
    "require_tenant",
]
