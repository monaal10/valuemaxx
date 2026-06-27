"""PgReconciliationRepository — APPEND-ONLY true-up records (§5.3).

Fulfils :class:`~valuemaxx.core.repositories.ReconciliationRepository` (virtual
subclass). There is deliberately NO update/mutate/replace/delete method: reconciliation
is additive and never an UPDATE to an estimate. ``append`` inserts a new record (two
appends for the same match key yield two rows — the history is preserved);
``list_for_match_key`` returns every record for a match key, newest first; and
``list_drift_alerts`` surfaces the >10% drifts (§5.3) computed from the latest record
per match key.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import select
from valuemaxx.core.reconciliation import DriftAlert
from valuemaxx.core.repositories import ReconciliationRepository
from valuemaxx.store import mappers
from valuemaxx.store.repositories._base import BaseRepository, as_row
from valuemaxx.store.tables import reconciliation_record as recon_table
from valuemaxx.store.tenant_guard import require_tenant

if TYPE_CHECKING:
    from collections.abc import Sequence

    from valuemaxx.core.ids import TenantId
    from valuemaxx.core.reconciliation import ReconciliationRecord

# >10% drift = a real miscount that must be alerted (§5.3); <=10% is rounding noise.
_DRIFT_ALERT_THRESHOLD = Decimal(10)


class PgReconciliationRepository(BaseRepository):
    """Append-only async persistence (virtual ``ReconciliationRepository``)."""

    async def append(self, tenant_id: TenantId, record: ReconciliationRecord) -> None:
        """Append a reconciliation record (additive; never updates an estimate)."""
        values = mappers.reconciliation_record_to_row(tenant_id, record)
        async with self._sessions.begin() as session:
            await session.execute(recon_table.insert().values(**values))

    async def list_for_match_key(
        self, tenant_id: TenantId, match_key: tuple[str, str, str, str, str]
    ) -> Sequence[ReconciliationRecord]:
        """List every reconciliation record for a match key, newest first."""
        provider, project, model_name, token_class, day = match_key
        stmt = (
            require_tenant(select(recon_table), tenant_id, recon_table)
            .where(recon_table.c.match_provider == provider)
            .where(recon_table.c.match_project == project)
            .where(recon_table.c.match_model == model_name)
            .where(recon_table.c.match_token_class == token_class)
            .where(recon_table.c.match_day == day)
            .order_by(recon_table.c.created_at.desc())
        )
        async with self._sessions() as session:
            rows = (await session.execute(stmt)).mappings().all()
        return [mappers.row_to_reconciliation_record(as_row(row)) for row in rows]

    async def list_drift_alerts(self, tenant_id: TenantId) -> Sequence[DriftAlert]:
        """List the open >10% drift alerts for the tenant (§5.3).

        The alert reflects the *latest* record per match key (the most recent true-up),
        so a re-reconciliation that brings drift back under threshold clears the alert.
        """
        stmt = require_tenant(select(recon_table), tenant_id, recon_table).order_by(
            recon_table.c.created_at.desc()
        )
        async with self._sessions() as session:
            rows = (await session.execute(stmt)).mappings().all()

        alerts: list[DriftAlert] = []
        seen: set[tuple[str, str, str, str, str]] = set()
        for row in rows:
            record = mappers.row_to_reconciliation_record(as_row(row))
            if record.match_key in seen:
                continue  # only the latest record per match key drives the alert
            seen.add(record.match_key)
            if abs(record.drift_pct) > _DRIFT_ALERT_THRESHOLD and record.drift_cause_ranked:
                alerts.append(
                    DriftAlert(
                        match_key=record.match_key,
                        drift_pct=record.drift_pct,
                        ranked_causes=record.drift_cause_ranked,
                    )
                )
        return alerts


ReconciliationRepository.register(PgReconciliationRepository)

__all__ = ["PgReconciliationRepository"]
