"""PgAllocationRepository — replace lines per run, rollup round-trip, quarantine flag."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from valuemaxx.core.allocation import AllocatedLine, AllocatedRollup
from valuemaxx.core.enums import (
    AllocationTier,
    BindingTier,
    ConfidenceLabel,
    Provenance,
)
from valuemaxx.core.ids import RunId, TenantId
from valuemaxx.core.reconciliation import ProvenanceBreakdown
from valuemaxx.core.rollup import RollupConfidence
from valuemaxx.store.repositories.allocation import PgAllocationRepository

from tests.unit.conftest import make_tenant

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


def _direct_line(amount: str) -> AllocatedLine:
    return AllocatedLine(
        tier=AllocationTier.DIRECT,
        label=Provenance.MEASURED,
        amount_usd=Decimal(amount),
        allocation_key=None,
        confidence=ConfidenceLabel.HIGH,
        sensitivity_pct=None,
        rule_version=None,
        quarantined=False,
    )


def _quarantined_line(amount: str) -> AllocatedLine:
    return AllocatedLine(
        tier=AllocationTier.FIXED_OVERHEAD,
        label=Provenance.ALLOCATED,
        amount_usd=Decimal(amount),
        allocation_key=None,
        confidence=ConfidenceLabel.LOW,
        sensitivity_pct=Decimal("12.5000000000"),
        rule_version="v1",
        quarantined=True,
    )


def _rollup(tenant: TenantId, run: str, lines: tuple[AllocatedLine, ...]) -> AllocatedRollup:
    return AllocatedRollup(
        tenant_id=tenant,
        run_id=RunId(run),
        lines=lines,
        pct_unallocated=Decimal("25.0000000000"),
        confidence=RollupConfidence(
            minimum_tier=BindingTier.EXACT,
            confidence_distribution={BindingTier.EXACT: 1},
        ),
        provenance_breakdown=ProvenanceBreakdown(
            reconciled_usd=Decimal("10.0000000000"),
            provisional_usd=Decimal("0.0000000000"),
            estimate_only_usd=Decimal("0.0000000000"),
        ),
    )


@pytest.mark.asyncio
async def test_upsert_lines_then_list(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant = make_tenant()
    repo = PgAllocationRepository(sessionmaker)
    lines = [_direct_line("1.0000000000"), _quarantined_line("2.0000000000")]
    await repo.upsert_lines(tenant, RunId("run-1"), lines)
    got = await repo.list_for_run(tenant, RunId("run-1"))
    assert list(got) == lines


@pytest.mark.asyncio
async def test_upsert_lines_replaces_previous(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant = make_tenant()
    repo = PgAllocationRepository(sessionmaker)
    await repo.upsert_lines(tenant, RunId("run-1"), [_direct_line("1.0000000000")])
    await repo.upsert_lines(
        tenant, RunId("run-1"), [_direct_line("9.0000000000"), _direct_line("8.0000000000")]
    )
    got = await repo.list_for_run(tenant, RunId("run-1"))
    assert [line.amount_usd for line in got] == [Decimal("9.0000000000"), Decimal("8.0000000000")]


@pytest.mark.asyncio
async def test_idle_quarantine_flag_persists(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant = make_tenant()
    repo = PgAllocationRepository(sessionmaker)
    await repo.upsert_lines(tenant, RunId("run-1"), [_quarantined_line("3.0000000000")])
    got = await repo.list_for_run(tenant, RunId("run-1"))
    assert got[0].quarantined is True
    assert got[0].tier is AllocationTier.FIXED_OVERHEAD


@pytest.mark.asyncio
async def test_rollup_roundtrips(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant = make_tenant()
    repo = PgAllocationRepository(sessionmaker)
    rollup = _rollup(tenant, "run-1", (_direct_line("1.0000000000"),))
    await repo.upsert_rollup(tenant, rollup)
    assert await repo.get_rollup(tenant, RunId("run-1")) == rollup


@pytest.mark.asyncio
async def test_get_rollup_missing_returns_none(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant = make_tenant()
    repo = PgAllocationRepository(sessionmaker)
    assert await repo.get_rollup(tenant, RunId("nope")) is None


@pytest.mark.asyncio
async def test_tenant_isolation_on_lines(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant_a = make_tenant()
    tenant_b = make_tenant()
    repo = PgAllocationRepository(sessionmaker)
    await repo.upsert_lines(tenant_a, RunId("run-1"), [_direct_line("1.0000000000")])
    assert await repo.list_for_run(tenant_b, RunId("run-1")) == []
