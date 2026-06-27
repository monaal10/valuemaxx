"""The table schema — the STORE-1 migration sub-barrier artifact (§9, §3.2).

One :class:`~sqlalchemy.MetaData` holding every table, mirroring the core domain
models one-to-one. This module is the single source the alembic migrations and the
``env.py`` ``target_metadata`` both point at, so ``alembic upgrade head`` followed
by ``--autogenerate`` yields an empty diff (the ``migration_no_autogen_drift``
conformance rule).

Schema invariants encoded here:
  * every table has ``tenant_id UUID NOT NULL`` plus a leading ``tenant_id`` index —
    row-level tenant scope is structural (§3.2);
  * money is ``NUMERIC(20, 10)`` (never ``Float``) — see :mod:`valuemaxx.store.types_pg`;
  * timestamps are ``TIMESTAMP(timezone=True)`` — naive datetimes are unstorable;
  * ``valuemaxx_cost_event`` has ``UNIQUE(tenant_id, run_id, attempt_id)`` — the
    idempotency key that drives the at-least-once upsert (M7);
  * ``valuemaxx_outcome_event`` has ``UNIQUE(tenant_id, correlation_id)`` — dedup on
    the round-tripped correlation id;
  * ``valuemaxx_reconciliation_record`` is **append-only**: primary key only, NO
    unique constraint, because reconciliation is additive and never an UPDATE (§5.3);
  * the raw-replay payloads (``raw``/``entity_keys``/``payload``) are JSON(B), so
    arbitrary nested structure round-trips unmodified for replay (§9).

Table identifiers carry the ``valuemaxx_`` prefix (the project's canonical
identity) so they never collide with an application's own tables in a shared schema.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    Uuid,
)
from valuemaxx.store.types_pg import jsonb, money

if TYPE_CHECKING:
    from uuid import UUID

metadata = MetaData()


def _tenant_id_column() -> Column[UUID]:
    """The required, non-nullable ``tenant_id`` column shared by every table."""
    return Column("tenant_id", Uuid(), nullable=False)


run = Table(
    "valuemaxx_run",
    metadata,
    Column("id", String(), primary_key=True),
    _tenant_id_column(),
    Column("agent_name", String(), nullable=True),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("ended_at", DateTime(timezone=True), nullable=True),
    # entity_keys is a JSON list of [type, value] pairs (a frozenset of tuples in core).
    Column("entity_keys", jsonb(), nullable=False),
    Index("ix_valuemaxx_run_tenant", "tenant_id"),
)


cost_event = Table(
    "valuemaxx_cost_event",
    metadata,
    Column("id", String(), primary_key=True),
    _tenant_id_column(),
    Column("run_id", String(), nullable=False),
    Column("attempt_id", String(), nullable=False),
    Column("provider", String(), nullable=False),
    Column("model", String(), nullable=False),
    # the six token classes (§5.2), each a non-negative integer.
    Column("input_uncached", Integer(), nullable=False),
    Column("cache_read", Integer(), nullable=False),
    Column("cache_write_5m", Integer(), nullable=False),
    Column("cache_write_1h", Integer(), nullable=False),
    Column("output", Integer(), nullable=False),
    Column("reasoning", Integer(), nullable=False),
    Column("capture_granularity", String(), nullable=False),
    # the provenance honesty axis, denormalised onto the row.
    Column("provenance", String(), nullable=False),
    Column("reconciliation_record_id", String(), nullable=True),
    Column("provenance_note", String(), nullable=True),
    Column("cost_usd", money(), nullable=True),  # None when billing-uncertain (PTU, H10)
    Column("is_streaming", Boolean(), nullable=False),
    Column("partial_recovered", Boolean(), nullable=False),
    Column("billing_uncertain_abort", Boolean(), nullable=False),
    Column("provenance_warnings", jsonb(), nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    # the idempotency key (M7) — at-least-once ingest never double-counts.
    UniqueConstraint(
        "tenant_id",
        "run_id",
        "attempt_id",
        name="uq_valuemaxx_cost_event_idem",
    ),
    Index("ix_valuemaxx_cost_event_tenant", "tenant_id"),
    Index("ix_valuemaxx_cost_event_run", "tenant_id", "run_id"),
    # match-key index for the reconciliation window scan (§5.3).
    Index("ix_valuemaxx_cost_event_matchkey", "provider", "model", "occurred_at"),
)


outcome_event = Table(
    "valuemaxx_outcome_event",
    metadata,
    Column("id", String(), primary_key=True),
    _tenant_id_column(),
    Column("name", String(), nullable=False),
    Column("signal_class", String(), nullable=False),
    Column("value", money(), nullable=True),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    # the (possibly unbound) outcome->run binding, denormalised.
    Column("bound_run_id", String(), nullable=True),
    Column("bound_tier", String(), nullable=True),
    Column("bound_by", String(), nullable=True),
    Column("entity_keys", jsonb(), nullable=False),
    Column("correlation_id", String(), nullable=True),
    Column("source", String(), nullable=False),
    Column("raw", jsonb(), nullable=False),
    # UNIQUE(tenant_id, correlation_id) — dedup on the round-tripped id. correlation_id
    # is nullable; standard SQL treats NULLs as distinct, so any number of unbound
    # outcomes (no correlation_id) coexist while a present correlation_id stays unique.
    UniqueConstraint(
        "tenant_id",
        "correlation_id",
        name="uq_valuemaxx_outcome_event_correlation",
    ),
    Index("ix_valuemaxx_outcome_event_tenant", "tenant_id"),
)


attribution_result = Table(
    "valuemaxx_attribution_result",
    metadata,
    # one result per (tenant, outcome) — outcome_id is the natural key.
    Column("outcome_id", String(), primary_key=True),
    _tenant_id_column(),
    Column("run_id", String(), nullable=True),
    Column("tier", String(), nullable=True),
    Column("bound_by", String(), nullable=True),
    Column("candidates", jsonb(), nullable=False),
    Column("review_required", Boolean(), nullable=False),
    Index("ix_valuemaxx_attribution_result_tenant", "tenant_id"),
)


reconciliation_record = Table(
    "valuemaxx_reconciliation_record",
    metadata,
    # PRIMARY KEY only — NO unique constraint: this table is append-only (§5.3).
    Column("id", String(), primary_key=True),
    _tenant_id_column(),
    # match_key = (provider, project/workspace, model, token_class, day).
    Column("match_provider", String(), nullable=False),
    Column("match_project", String(), nullable=False),
    Column("match_model", String(), nullable=False),
    Column("match_token_class", String(), nullable=False),
    Column("match_day", String(), nullable=False),
    Column("estimated_total", money(), nullable=False),
    Column("billed_total", money(), nullable=False),
    Column("proration_factor", money(), nullable=False),
    Column("drift_pct", money(), nullable=False),
    Column("drift_cause_ranked", jsonb(), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Index("ix_valuemaxx_reconciliation_record_tenant", "tenant_id"),
    Index(
        "ix_valuemaxx_reconciliation_record_matchkey",
        "tenant_id",
        "match_provider",
        "match_project",
        "match_model",
        "match_token_class",
        "match_day",
    ),
)


allocation_line = Table(
    "valuemaxx_allocation_line",
    metadata,
    Column("id", String(), primary_key=True),
    _tenant_id_column(),
    Column("run_id", String(), nullable=False),
    Column("ordinal", Integer(), nullable=False),  # preserves line order within a run
    Column("tier", String(), nullable=False),
    Column("label", String(), nullable=False),
    Column("amount_usd", money(), nullable=False),
    Column("allocation_key", String(), nullable=True),
    Column("confidence", String(), nullable=False),
    Column("sensitivity_pct", money(), nullable=True),
    Column("rule_version", String(), nullable=True),
    Column("quarantined", Boolean(), nullable=False),
    Index("ix_valuemaxx_allocation_line_tenant", "tenant_id"),
    Index("ix_valuemaxx_allocation_line_run", "tenant_id", "run_id"),
)


raw_record = Table(
    "valuemaxx_raw_record",
    metadata,
    Column("id", String(), primary_key=True),
    _tenant_id_column(),
    # the JSONB payload preserved unmodified for inference-matching + replay (§9).
    Column("payload", jsonb(), nullable=False),
    Column("entity_keys", jsonb(), nullable=False),
    Index("ix_valuemaxx_raw_record_tenant", "tenant_id"),
)


eval_dataset = Table(
    "valuemaxx_eval_dataset",
    metadata,
    Column("id", String(), primary_key=True),
    _tenant_id_column(),
    Column("name", String(), nullable=False),
    Column("version", Integer(), nullable=False),
    Column("cases", jsonb(), nullable=False),
    Index("ix_valuemaxx_eval_dataset_tenant", "tenant_id"),
)


eval_recommendation = Table(
    "valuemaxx_eval_recommendation",
    metadata,
    Column("id", String(), primary_key=True),
    _tenant_id_column(),
    Column("recommended_model", String(), nullable=True),
    Column("incumbent_model", String(), nullable=False),
    Column("grade", String(), nullable=False),
    Column("label_source", String(), nullable=False),
    Column("payload", jsonb(), nullable=False),  # the full recommendation artifact
    Index("ix_valuemaxx_eval_recommendation_tenant", "tenant_id"),
    Index(
        "ix_valuemaxx_eval_recommendation_incumbent",
        "tenant_id",
        "incumbent_model",
    ),
)


review_queue = Table(
    "valuemaxx_review_queue",
    metadata,
    Column("id", String(), primary_key=True),
    _tenant_id_column(),
    Column("item", jsonb(), nullable=False),
    Column("enqueued_at", DateTime(timezone=True), nullable=False),
    Index("ix_valuemaxx_review_queue_tenant", "tenant_id"),
)


__all__ = [
    "allocation_line",
    "attribution_result",
    "cost_event",
    "eval_dataset",
    "eval_recommendation",
    "metadata",
    "outcome_event",
    "raw_record",
    "reconciliation_record",
    "review_queue",
    "run",
]
