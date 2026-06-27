"""Concrete async SQLAlchemy repositories — one per core repository ABC.

Each ``Pg*Repository`` fulfils the matching ABC from ``valuemaxx.core``
(``RunRepository``, ``CostEventRepository``, ...) as a registered *virtual* subclass
(the ABCs are synchronous; the real layer is async), is tenant-scoped through
``tenant_guard.require_tenant``, and is constructed from an ``async_sessionmaker``.
"""

from __future__ import annotations

from valuemaxx.store.repositories.allocation import PgAllocationRepository
from valuemaxx.store.repositories.attribution import PgAttributionResultRepository
from valuemaxx.store.repositories.cost_event import PgCostEventRepository
from valuemaxx.store.repositories.eval_dataset import PgEvalDatasetRepository
from valuemaxx.store.repositories.eval_recommendation import PgEvalRecommendationRepository
from valuemaxx.store.repositories.outcome_event import PgOutcomeEventRepository
from valuemaxx.store.repositories.raw_record import PgRawRecordRepository
from valuemaxx.store.repositories.reconciliation import PgReconciliationRepository
from valuemaxx.store.repositories.review_queue import PgReviewQueue
from valuemaxx.store.repositories.run import PgRunRepository

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
]
