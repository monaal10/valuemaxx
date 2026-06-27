"""STORE-1 — the table schema artifact (the migration sub-barrier deliverable).

These assert the *shape* of the SQLAlchemy Core MetaData that every migration and
every repository mirrors: money is NUMERIC (never Float), timestamps are
timezone-aware, the raw/entity-key columns are JSON(B), tenant_id is NOT NULL on
every table with a leading index, the cost-event idempotency key is a unique
constraint, and the reconciliation table is append-only (no unique constraint).
"""

from __future__ import annotations

from sqlalchemy import DateTime, Numeric, UniqueConstraint
from sqlalchemy.sql.sqltypes import Float
from valuemaxx.store.tables import (
    allocation_line,
    attribution_result,
    cost_event,
    eval_dataset,
    eval_recommendation,
    metadata,
    outcome_event,
    raw_record,
    reconciliation_record,
    review_queue,
    run,
)

_ALL_TABLES = (
    run,
    cost_event,
    outcome_event,
    attribution_result,
    reconciliation_record,
    allocation_line,
    raw_record,
    eval_dataset,
    eval_recommendation,
    review_queue,
)


def test_all_tables_registered_on_one_metadata() -> None:
    """Every table is registered on the single shared MetaData (env.py target)."""
    names = set(metadata.tables)
    for table in _ALL_TABLES:
        assert table.name in names


def test_every_table_has_tenant_id_not_null() -> None:
    """tenant_id is a required, non-nullable column on every table (§3.2)."""
    for table in _ALL_TABLES:
        assert "tenant_id" in table.c, f"{table.name} missing tenant_id"
        assert table.c.tenant_id.nullable is False, f"{table.name}.tenant_id is nullable"


def test_every_table_has_a_leading_tenant_index() -> None:
    """Every table carries an index whose first column is tenant_id (row-level scope)."""
    for table in _ALL_TABLES:
        leading: set[str] = set()
        for idx in table.indexes:
            cols = list(idx.columns)
            if cols:
                leading.add(cols[0].name)
        assert "tenant_id" in leading, f"{table.name} has no leading tenant_id index"


def test_money_columns_are_numeric_not_float() -> None:
    """Every money column is NUMERIC(20, 10) — never Float (M7, no binary drift)."""
    money_columns = (
        cost_event.c.cost_usd,
        outcome_event.c.value,
        reconciliation_record.c.estimated_total,
        reconciliation_record.c.billed_total,
        reconciliation_record.c.proration_factor,
        reconciliation_record.c.drift_pct,
        allocation_line.c.amount_usd,
    )
    for col in money_columns:
        assert isinstance(col.type, Numeric), f"{col} is not Numeric"
        assert not isinstance(col.type, Float), f"{col} is a Float — money must be Numeric"
        assert col.type.precision == 20, f"{col} precision != 20"
        assert col.type.scale == 10, f"{col} scale != 10"


def test_timestamps_are_timezone_aware() -> None:
    """Timestamp columns carry tz=True so naive datetimes can never be stored."""
    ts_columns = (
        run.c.started_at,
        cost_event.c.occurred_at,
        outcome_event.c.occurred_at,
        reconciliation_record.c.created_at,
    )
    for col in ts_columns:
        assert isinstance(col.type, DateTime), f"{col} is not DateTime"
        assert col.type.timezone is True, f"{col} is not timezone-aware"


def test_cost_event_has_idempotency_unique_constraint() -> None:
    """cost_event carries UNIQUE(tenant_id, run_id, attempt_id) — drives upsert (M7)."""
    uniques = [
        {c.name for c in con.columns}
        for con in cost_event.constraints
        if isinstance(con, UniqueConstraint)
    ]
    assert {"tenant_id", "run_id", "attempt_id"} in uniques


def test_outcome_event_has_correlation_unique_constraint() -> None:
    """outcome_event carries UNIQUE(tenant_id, correlation_id) — dedup on round-tripped id."""
    uniques = [
        {c.name for c in con.columns}
        for con in outcome_event.constraints
        if isinstance(con, UniqueConstraint)
    ]
    assert {"tenant_id", "correlation_id"} in uniques


def test_reconciliation_record_has_no_unique_constraint() -> None:
    """reconciliation_record is append-only: PK only, NO unique constraint (§5.3)."""
    uniques = [
        con for con in reconciliation_record.constraints if isinstance(con, UniqueConstraint)
    ]
    assert uniques == [], "reconciliation_record must be append-only (no unique constraint)"


def test_jsonb_columns_present() -> None:
    """The raw/entity-key columns are JSON(B) for preserved replay payloads (§9)."""
    json_columns = (
        outcome_event.c.raw,
        outcome_event.c.entity_keys,
        raw_record.c.payload,
        raw_record.c.entity_keys,
    )
    for col in json_columns:
        type_name = col.type.__class__.__name__.lower()
        assert "json" in type_name, f"{col} is {col.type!r}, expected a JSON(B) type"
