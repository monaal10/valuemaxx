"""PgEvalRecommendationRepository — eval recommendations stored as JSON artifacts (§8.6).

Fulfils :class:`~valuemaxx.core.eval.EvalRecommendationRepository` (virtual subclass).
A recommendation has no natural id, so the row id is derived deterministically from
``(incumbent_model, recommended_model)`` — re-upserting the same comparison overwrites
rather than accumulating duplicates. The full artifact (confidence label, parity CI,
latencies, disagreements) is stored as JSON and round-trips exactly. ``list_for_incumbent``
is tenant-scoped and filtered to the incumbent column.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select
from valuemaxx.core.eval import EvalRecommendation
from valuemaxx.core.eval.repositories import EvalRecommendationRepository
from valuemaxx.store.repositories._base import BaseRepository, as_row, upsert_stmt
from valuemaxx.store.tables import eval_recommendation as rec_table
from valuemaxx.store.tenant_guard import require_tenant

if TYPE_CHECKING:
    from collections.abc import Sequence

    from valuemaxx.core.ids import TenantId

_CONFLICT_KEY = ["tenant_id", "id"]


def _row_id(rec: EvalRecommendation) -> str:
    """Deterministic surrogate id so re-upserting the same comparison is idempotent."""
    return f"{rec.incumbent_model}->{rec.recommended_model}"


class PgEvalRecommendationRepository(BaseRepository):
    """Async persistence for eval recommendations (virtual ``EvalRecommendationRepository``)."""

    async def upsert(self, tenant_id: TenantId, recommendation: EvalRecommendation) -> None:
        """Insert or update a recommendation (idempotent on incumbent->recommended)."""
        values: dict[str, object] = {
            "id": _row_id(recommendation),
            "tenant_id": tenant_id,
            "recommended_model": recommendation.recommended_model,
            "incumbent_model": recommendation.incumbent_model,
            "grade": recommendation.grade.value,
            "label_source": recommendation.label_source.value,
            "payload": recommendation.model_dump(mode="json"),
        }
        async with self._sessions.begin() as session:
            await session.execute(upsert_stmt(session, rec_table, values, _CONFLICT_KEY))

    async def list_for_incumbent(
        self, tenant_id: TenantId, incumbent_model: str
    ) -> Sequence[EvalRecommendation]:
        """List recommendations evaluated against an incumbent model (tenant-scoped)."""
        stmt = require_tenant(select(rec_table), tenant_id, rec_table).where(
            rec_table.c.incumbent_model == incumbent_model
        )
        async with self._sessions() as session:
            rows = (await session.execute(stmt)).mappings().all()
        return [
            EvalRecommendation.model_validate(as_row(row)["payload"], strict=False)
            for row in rows
        ]


EvalRecommendationRepository.register(PgEvalRecommendationRepository)

__all__ = ["PgEvalRecommendationRepository"]
