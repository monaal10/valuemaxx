"""PgReconciliationRepository — append-only history + >10% drift alerts (§5.3)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import func, select
from valuemaxx.core.ids import ReconciliationRecordId, TenantId
from valuemaxx.core.reconciliation import ReconciliationRecord
from valuemaxx.store.repositories.reconciliation import PgReconciliationRepository
from valuemaxx.store.tables import reconciliation_record as recon_table

from tests.unit.conftest import make_tenant

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

_MATCH = ("anthropic", "proj-1", "claude-opus-4", "output", "2026-06-27")


def _record(
    tenant: TenantId,
    *,
    record_id: str,
    drift: str = "1.0000000000",
    causes: tuple[str, ...] = ("cache_mispricing",),
    when: datetime | None = None,
) -> ReconciliationRecord:
    return ReconciliationRecord(
        tenant_id=tenant,
        id=ReconciliationRecordId(record_id),
        match_key=_MATCH,
        estimated_total=Decimal("100.0000000000"),
        billed_total=Decimal("101.0000000000"),
        proration_factor=Decimal("1.0100000000"),
        drift_pct=Decimal(drift),
        drift_cause_ranked=causes,
        created_at=when or datetime(2026, 6, 27, 0, 0, tzinfo=UTC),
    )


async def _count(sessionmaker: async_sessionmaker[AsyncSession]) -> int:
    async with sessionmaker() as session:
        return (
            await session.execute(select(func.count()).select_from(recon_table))
        ).scalar_one()


@pytest.mark.asyncio
async def test_two_appends_same_match_key_yield_two_rows(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """Append-only: re-reconciling a match key adds a row, never overwrites (§5.3)."""
    tenant = make_tenant()
    repo = PgReconciliationRepository(sessionmaker)
    await repo.append(tenant, _record(tenant, record_id="rr-1"))
    await repo.append(tenant, _record(tenant, record_id="rr-2"))
    assert await _count(sessionmaker) == 2
    records = await repo.list_for_match_key(tenant, _MATCH)
    assert len(records) == 2


@pytest.mark.asyncio
async def test_list_for_match_key_newest_first(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant = make_tenant()
    repo = PgReconciliationRepository(sessionmaker)
    await repo.append(
        tenant, _record(tenant, record_id="rr-old", when=datetime(2026, 6, 27, tzinfo=UTC))
    )
    await repo.append(
        tenant, _record(tenant, record_id="rr-new", when=datetime(2026, 6, 28, tzinfo=UTC))
    )
    records = await repo.list_for_match_key(tenant, _MATCH)
    assert [r.id for r in records] == [
        ReconciliationRecordId("rr-new"),
        ReconciliationRecordId("rr-old"),
    ]


@pytest.mark.asyncio
async def test_drift_alert_only_above_threshold(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant = make_tenant()
    repo = PgReconciliationRepository(sessionmaker)
    await repo.append(tenant, _record(tenant, record_id="rr-1", drift="2.0000000000"))
    assert await repo.list_drift_alerts(tenant) == []
    await repo.append(
        tenant,
        _record(
            tenant,
            record_id="rr-2",
            drift="15.0000000000",
            causes=("negotiated_rate", "batch_discount"),
            when=datetime(2026, 6, 28, tzinfo=UTC),
        ),
    )
    alerts = await repo.list_drift_alerts(tenant)
    assert len(alerts) == 1
    assert alerts[0].drift_pct == Decimal("15.0000000000")
    assert alerts[0].ranked_causes == ("negotiated_rate", "batch_discount")


@pytest.mark.asyncio
async def test_re_reconcile_under_threshold_clears_alert(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """The latest record per match key drives the alert — a corrected true-up clears it."""
    tenant = make_tenant()
    repo = PgReconciliationRepository(sessionmaker)
    await repo.append(
        tenant,
        _record(
            tenant, record_id="rr-1", drift="20.0000000000", when=datetime(2026, 6, 27, tzinfo=UTC)
        ),
    )
    await repo.append(
        tenant,
        _record(
            tenant, record_id="rr-2", drift="1.0000000000", when=datetime(2026, 6, 28, tzinfo=UTC)
        ),
    )
    assert await repo.list_drift_alerts(tenant) == []


@pytest.mark.asyncio
async def test_repo_has_no_mutating_method() -> None:
    """The reconciliation repo exposes no update/mutate/replace/delete path (§5.3)."""
    public = {n for n in dir(PgReconciliationRepository) if not n.startswith("_")}
    forbidden = {"update", "mutate", "replace", "overwrite", "patch", "delete"}
    assert public & forbidden == set()
