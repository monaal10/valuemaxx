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
    optimization_baseline,
    optimization_deployment,
    optimization_experiment,
    optimization_finding,
    optimization_frontier,
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
    optimization_baseline,
    optimization_finding,
    optimization_frontier,
    optimization_experiment,
    optimization_deployment,
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


def test_tenant_id_is_part_of_every_primary_key() -> None:
    """tenant_id is a primary-key column on every table — no cross-tenant id collision.

    Regression for the bug where ``id`` alone was the PK: two tenants writing the same
    logical id clobbered each other's row (an upsert on tenant B overwrote tenant A's
    run). The composite ``(tenant_id, id)`` key makes that structurally impossible.
    """
    for table in _ALL_TABLES:
        pk_columns = {col.name for col in table.primary_key.columns}
        assert "tenant_id" in pk_columns, f"{table.name} PK does not include tenant_id"


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
        optimization_finding.c.estimated_savings_usd,
        optimization_frontier.c.cost_per_unit,
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
        optimization_baseline.c.activated_at,
        optimization_experiment.c.started_at,
        optimization_deployment.c.authorized_at,
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


def test_cost_event_has_nullable_config_stamp_columns() -> None:
    """Legacy events coexist with queryable gateway config stamps."""
    names = (
        "call_site_id",
        "system_hash",
        "tools_hash",
        "params_hash",
        "config_identity",
        "config_identity_weak",
        "http_status",
    )
    for name in names:
        assert name in cost_event.c
        assert cost_event.c[name].nullable is True


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


def test_experiment_has_one_active_per_call_site_index() -> None:
    """Only one pending/running/held experiment may occupy a call site's traffic."""
    active_indexes = [
        idx
        for idx in optimization_experiment.indexes
        if idx.name == "uq_valuemaxx_optimization_experiment_active_call_site"
    ]
    assert len(active_indexes) == 1
    index = active_indexes[0]
    assert index.unique is True
    assert [column.name for column in index.columns] == ["tenant_id", "call_site_id"]


def test_jsonb_columns_present() -> None:
    """The raw/entity-key columns are JSON(B) for preserved replay payloads (§9)."""
    json_columns = (
        outcome_event.c.raw,
        outcome_event.c.entity_keys,
        raw_record.c.payload,
        raw_record.c.entity_keys,
        optimization_baseline.c.payload,
        optimization_finding.c.payload,
        optimization_frontier.c.payload,
        optimization_experiment.c.payload,
        optimization_deployment.c.payload,
    )
    for col in json_columns:
        type_name = col.type.__class__.__name__.lower()
        assert "json" in type_name, f"{col} is {col.type!r}, expected a JSON(B) type"
