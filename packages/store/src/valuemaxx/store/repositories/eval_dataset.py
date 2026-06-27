"""PgEvalDatasetRepository — versioned eval datasets stored as JSON artifacts (§8.3).

Fulfils :class:`~valuemaxx.core.eval.EvalDatasetRepository` (virtual subclass). Each
dataset is stored as one row per ``(tenant_id, id)`` carrying the full dataset JSON
(the stratified cases round-trip exactly); ``upsert`` overwrites with the newest
version so ``get`` returns the latest. Reads are tenant-scoped.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select
from valuemaxx.core.eval import EvalDataset
from valuemaxx.core.eval.repositories import EvalDatasetRepository
from valuemaxx.store.repositories._base import BaseRepository, upsert_stmt
from valuemaxx.store.tables import eval_dataset as dataset_table
from valuemaxx.store.tenant_guard import require_tenant

if TYPE_CHECKING:
    from valuemaxx.core.ids import TenantId

_CONFLICT_KEY = ["tenant_id", "id"]


class PgEvalDatasetRepository(BaseRepository):
    """Async persistence for eval datasets (virtual ``EvalDatasetRepository``)."""

    async def upsert(self, tenant_id: TenantId, dataset: EvalDataset) -> None:
        """Insert or update an eval dataset (latest version wins on the id)."""
        values: dict[str, object] = {
            "id": dataset.id,
            "tenant_id": tenant_id,
            "name": dataset.name,
            "version": dataset.version,
            "cases": dataset.model_dump(mode="json")["cases"],
        }
        async with self._sessions.begin() as session:
            await session.execute(upsert_stmt(session, dataset_table, values, _CONFLICT_KEY))

    async def get(self, tenant_id: TenantId, dataset_id: str) -> EvalDataset | None:
        """Fetch the latest version of a dataset by id within the tenant scope, or None."""
        stmt = require_tenant(select(dataset_table), tenant_id, dataset_table).where(
            dataset_table.c.id == dataset_id
        )
        async with self._sessions() as session:
            row = (await session.execute(stmt)).mappings().one_or_none()
        if row is None:
            return None
        # strict=False: the JSON payload carries enums/values as strings (we serialized
        # it with model_dump(mode="json")); core models are strict on direct construction.
        return EvalDataset.model_validate(
            {
                "tenant_id": row["tenant_id"],
                "id": row["id"],
                "name": row["name"],
                "version": row["version"],
                "cases": row["cases"],
            },
            strict=False,
        )


EvalDatasetRepository.register(PgEvalDatasetRepository)

__all__ = ["PgEvalDatasetRepository"]
