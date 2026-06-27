"""Real-Postgres integration (H2) — JSONB fidelity, migration drift, idempotent upsert.

These run against a real ``postgres:16`` container (testcontainers); they are skipped
with a reason when Docker is unavailable (see conftest). They cover exactly what SQLite
cannot honestly stand in for: JSONB byte/structure round-trip, the alembic
autogenerate-empty-diff guarantee on the production dialect, and the idempotent upsert
+ append-only + tenant-isolation behaviour on real Postgres.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from valuemaxx.core.cost import CostEvent
from valuemaxx.core.enums import CaptureGranularity, Provenance, SignalClass
from valuemaxx.core.ids import (
    AttemptId,
    CostEventId,
    OutcomeEventId,
    ReconciliationRecordId,
    RunId,
    TenantId,
)
from valuemaxx.core.outcome import OutcomeBinding, OutcomeEvent
from valuemaxx.core.provenance import ProvenanceLabel
from valuemaxx.core.reconciliation import ReconciliationRecord
from valuemaxx.core.tokens import TokenVector
from valuemaxx.store.migrations_api import autogenerate_upgrade_ops
from valuemaxx.store.repositories.cost_event import PgCostEventRepository
from valuemaxx.store.repositories.outcome_event import PgOutcomeEventRepository
from valuemaxx.store.repositories.raw_record import PgRawRecordRepository
from valuemaxx.store.repositories.reconciliation import PgReconciliationRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


def _tenant() -> TenantId:
    return TenantId(uuid4())


_DEEP_PAYLOAD = {
    "messages": [
        {"role": "user", "content": "where is my order?"},
        {"role": "assistant", "content": "let me check", "tool_calls": [{"id": "t1"}]},
    ],
    "usage": {"input_tokens": 120, "output_tokens": 40, "cache": {"read": 10, "write": 0}},
    "meta": {"nested": {"deep": [1, 2, {"k": "v", "list": [True, None, 3.5]}]}},
    "unicode": "café — 日本語 — 😀",
}


def test_migration_no_autogen_drift_on_real_postgres(postgres_url: str) -> None:
    """After upgrade head on real Postgres, autogenerate yields an empty diff (STORE owns this).

    This is the authoritative migration-drift check on the production dialect: recon/
    alloc/metrics depend on these migrations and never autogenerate themselves.
    """
    from valuemaxx.store.migrations_api import upgrade_to_head

    upgrade_to_head(postgres_url)
    ops = autogenerate_upgrade_ops(postgres_url)
    assert ops == [], f"alembic autogenerate drift on Postgres: {ops}"


@pytest.mark.asyncio
async def test_raw_jsonb_roundtrips_identically(
    pg_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """A deeply-nested JSONB payload round-trips structure-identical on real Postgres (H2)."""
    tenant = _tenant()
    repo = PgRawRecordRepository(pg_sessionmaker)
    await repo.put(tenant, "rec-1", _DEEP_PAYLOAD, frozenset({("ticket", "T-1")}))
    assert await repo.get(tenant, "rec-1") == _DEEP_PAYLOAD


@pytest.mark.asyncio
async def test_outcome_raw_jsonb_roundtrips(
    pg_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """The outcome.raw JSONB map round-trips identically on real Postgres."""
    tenant = _tenant()
    repo = PgOutcomeEventRepository(pg_sessionmaker)
    outcome = OutcomeEvent(
        tenant_id=tenant,
        id=OutcomeEventId("oe-1"),
        name="loan_funded",
        signal_class=SignalClass.OUTCOME_CONFIRMED,
        value=Decimal("50000.0000000000"),
        occurred_at=datetime(2026, 6, 27, 12, 0, tzinfo=UTC),
        binding=OutcomeBinding(run_id=None, tier=None, bound_by=None),
        entity_keys=frozenset({("application", "A-1")}),
        correlation_id=None,
        source="webhook",
        raw=_DEEP_PAYLOAD,
    )
    await repo.upsert(tenant, outcome)
    assert await repo.get(tenant, OutcomeEventId("oe-1")) == outcome


def _cost_event(tenant: TenantId, *, cost: Decimal) -> CostEvent:
    return CostEvent(
        tenant_id=tenant,
        id=CostEventId("ce-1"),
        run_id=RunId("run-1"),
        attempt_id=AttemptId("att-1"),
        provider="anthropic",
        model="claude-opus-4",
        tokens=TokenVector(
            input_uncached=100,
            cache_read=20,
            cache_write_5m=5,
            cache_write_1h=3,
            output=50,
            reasoning=10,
        ),
        capture_granularity=CaptureGranularity.PER_ATTEMPT,
        provenance=ProvenanceLabel(provenance=Provenance.MEASURED),
        cost_usd=cost,
        is_streaming=True,
        partial_recovered=False,
        billing_uncertain_abort=False,
        provenance_warnings=(),
        occurred_at=datetime(2026, 6, 27, 12, 0, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_idempotent_upsert_decimal_fidelity_on_postgres(
    pg_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """Double upsert of the same idempotency key => one row, exact Decimal preserved (M7)."""
    tenant = _tenant()
    repo = PgCostEventRepository(pg_sessionmaker)
    await repo.upsert(tenant, _cost_event(tenant, cost=Decimal("0.0123456789")))
    await repo.upsert(tenant, _cost_event(tenant, cost=Decimal("0.9876543210")))
    found = await repo.list_for_run(tenant, RunId("run-1"))
    assert len(found) == 1
    assert found[0].cost_usd == Decimal("0.9876543210")


@pytest.mark.asyncio
async def test_reconciliation_append_only_on_postgres(
    pg_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """Two appends for the same match key yield two rows on real Postgres (§5.3)."""
    tenant = _tenant()
    repo = PgReconciliationRepository(pg_sessionmaker)
    match = ("anthropic", "proj-1", "claude-opus-4", "output", "2026-06-27")
    for rid in ("rr-1", "rr-2"):
        await repo.append(
            tenant,
            ReconciliationRecord(
                tenant_id=tenant,
                id=ReconciliationRecordId(rid),
                match_key=match,
                estimated_total=Decimal("100.0000000000"),
                billed_total=Decimal("101.0000000000"),
                proration_factor=Decimal("1.0100000000"),
                drift_pct=Decimal("1.0000000000"),
                drift_cause_ranked=("cache_mispricing",),
                created_at=datetime(2026, 6, 27, 0, 0, tzinfo=UTC),
            ),
        )
    records = await repo.list_for_match_key(tenant, match)
    assert len(records) == 2


@pytest.mark.asyncio
async def test_tenant_isolation_on_postgres(
    pg_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """Tenant A's cost events are invisible to tenant B on real Postgres."""
    tenant_a = _tenant()
    tenant_b = _tenant()
    repo = PgCostEventRepository(pg_sessionmaker)
    await repo.upsert(tenant_a, _cost_event(tenant_a, cost=Decimal("0.0100000000")))
    assert await repo.list_for_run(tenant_b, RunId("run-1")) == []
