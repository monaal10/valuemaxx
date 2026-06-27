"""Mappers — the boundary between core pydantic models and flat SQLAlchemy rows.

Each ``*_to_row`` flattens a frozen domain model into a column-keyed ``dict`` for an
INSERT/upsert; each ``row_to_*`` reconstructs the model from a row mapping. The
mappers own the lossy-looking conversions and make them lossless:

  * ``frozenset[tuple[str, str]]`` entity keys serialize to a *sorted* JSON list of
    ``[type, value]`` pairs (sorted so the stored bytes are deterministic) and
    deserialize back to a frozenset — set identity is preserved, ordering is not
    leaked;
  * ``Decimal`` money is carried through the ``NUMERIC`` column untouched (no float);
  * tuples (candidates, drift causes, provenance warnings) serialize as JSON lists;
  * the outcome ``OutcomeBinding`` and ``ProvenanceLabel`` are denormalised onto the
    row and rebuilt on read.

These are plain functions, not pydantic models, so they never trip the
``no_type_outside_core`` rule (the domain types stay in core).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from valuemaxx.core.attribution import AttributionCandidate, AttributionResult
from valuemaxx.core.cost import CostEvent
from valuemaxx.core.enums import BindingTier, CaptureGranularity, Provenance, SignalClass
from valuemaxx.core.ids import (
    AttemptId,
    CorrelationId,
    CostEventId,
    OutcomeEventId,
    ReconciliationRecordId,
    RunId,
)
from valuemaxx.core.outcome import OutcomeBinding, OutcomeEvent
from valuemaxx.core.provenance import ProvenanceLabel
from valuemaxx.core.reconciliation import ReconciliationRecord
from valuemaxx.core.run import Run
from valuemaxx.core.tokens import TokenVector

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime
    from decimal import Decimal

    from valuemaxx.core.ids import TenantId


# --- entity-key (de)serialisation -------------------------------------------------


def _entity_keys_to_json(keys: frozenset[tuple[str, str]]) -> list[list[str]]:
    """Serialise entity keys to a sorted JSON list of [type, value] pairs (deterministic)."""
    return [[k, v] for k, v in sorted(keys)]


def _entity_keys_from_json(value: object) -> frozenset[tuple[str, str]]:
    """Rebuild the entity-key frozenset from its JSON list-of-pairs form."""
    items = _as_json_list(value)
    pairs: set[tuple[str, str]] = set()
    for item in items:
        pair = _as_json_list(item)
        assert len(pair) == 2, "entity key must be a [type, value] pair"
        pairs.add((str(pair[0]), str(pair[1])))
    return frozenset(pairs)


def _str_tuple_from_json(value: object) -> tuple[str, ...]:
    """Rebuild a tuple[str, ...] from a JSON list."""
    return tuple(str(item) for item in _as_json_list(value))


# --- Run --------------------------------------------------------------------------


def run_to_row(tenant_id: TenantId, model: Run) -> dict[str, object]:
    """Flatten a :class:`~valuemaxx.core.run.Run` into a row dict."""
    return {
        "id": model.id,
        "tenant_id": tenant_id,
        "agent_name": model.agent_name,
        "started_at": model.started_at,
        "ended_at": model.ended_at,
        "entity_keys": _entity_keys_to_json(model.entity_keys),
    }


def row_to_run(row: Mapping[str, object]) -> Run:
    """Rebuild a :class:`~valuemaxx.core.run.Run` from a row mapping."""
    return Run(
        tenant_id=_as_tenant(row["tenant_id"]),
        id=RunId(_as_str(row["id"])),
        agent_name=_as_opt_str(row["agent_name"]),
        started_at=_as_dt(row["started_at"]),
        ended_at=_as_opt_dt(row["ended_at"]),
        entity_keys=_entity_keys_from_json(row["entity_keys"]),
    )


# --- CostEvent --------------------------------------------------------------------


def cost_event_to_row(tenant_id: TenantId, model: CostEvent) -> dict[str, object]:
    """Flatten a :class:`~valuemaxx.core.cost.CostEvent` into a row dict."""
    t = model.tokens
    p = model.provenance
    return {
        "id": model.id,
        "tenant_id": tenant_id,
        "run_id": model.run_id,
        "attempt_id": model.attempt_id,
        "provider": model.provider,
        "model": model.model,
        "input_uncached": t.input_uncached,
        "cache_read": t.cache_read,
        "cache_write_5m": t.cache_write_5m,
        "cache_write_1h": t.cache_write_1h,
        "output": t.output,
        "reasoning": t.reasoning,
        "capture_granularity": model.capture_granularity.value,
        "provenance": p.provenance.value,
        "reconciliation_record_id": p.reconciliation_record_id,
        "provenance_note": p.note,
        "cost_usd": model.cost_usd,
        "is_streaming": model.is_streaming,
        "partial_recovered": model.partial_recovered,
        "billing_uncertain_abort": model.billing_uncertain_abort,
        "provenance_warnings": list(model.provenance_warnings),
        "occurred_at": model.occurred_at,
    }


def row_to_cost_event(row: Mapping[str, object]) -> CostEvent:
    """Rebuild a :class:`~valuemaxx.core.cost.CostEvent` from a row mapping."""
    return CostEvent(
        tenant_id=_as_tenant(row["tenant_id"]),
        id=CostEventId(_as_str(row["id"])),
        run_id=RunId(_as_str(row["run_id"])),
        attempt_id=AttemptId(_as_str(row["attempt_id"])),
        provider=_as_str(row["provider"]),
        model=_as_str(row["model"]),
        tokens=TokenVector(
            input_uncached=_as_int(row["input_uncached"]),
            cache_read=_as_int(row["cache_read"]),
            cache_write_5m=_as_int(row["cache_write_5m"]),
            cache_write_1h=_as_int(row["cache_write_1h"]),
            output=_as_int(row["output"]),
            reasoning=_as_int(row["reasoning"]),
        ),
        capture_granularity=CaptureGranularity(_as_str(row["capture_granularity"])),
        provenance=ProvenanceLabel(
            provenance=Provenance(_as_str(row["provenance"])),
            reconciliation_record_id=_as_opt_str(row["reconciliation_record_id"]),
            note=_as_opt_str(row["provenance_note"]),
        ),
        cost_usd=_as_opt_decimal(row["cost_usd"]),
        is_streaming=_as_bool(row["is_streaming"]),
        partial_recovered=_as_bool(row["partial_recovered"]),
        billing_uncertain_abort=_as_bool(row["billing_uncertain_abort"]),
        provenance_warnings=_str_tuple_from_json(row["provenance_warnings"]),
        occurred_at=_as_dt(row["occurred_at"]),
    )


# --- OutcomeEvent -----------------------------------------------------------------


def outcome_event_to_row(tenant_id: TenantId, model: OutcomeEvent) -> dict[str, object]:
    """Flatten an :class:`~valuemaxx.core.outcome.OutcomeEvent` into a row dict."""
    b = model.binding
    return {
        "id": model.id,
        "tenant_id": tenant_id,
        "name": model.name,
        "signal_class": model.signal_class.value,
        "value": model.value,
        "occurred_at": model.occurred_at,
        "bound_run_id": b.run_id,
        "bound_tier": b.tier.value if b.tier is not None else None,
        "bound_by": b.bound_by,
        "entity_keys": _entity_keys_to_json(model.entity_keys),
        "correlation_id": model.correlation_id,
        "source": model.source,
        "raw": dict(model.raw),
    }


def row_to_outcome_event(row: Mapping[str, object]) -> OutcomeEvent:
    """Rebuild an :class:`~valuemaxx.core.outcome.OutcomeEvent` from a row mapping."""
    bound_run = _as_opt_str(row["bound_run_id"])
    bound_tier = _as_opt_str(row["bound_tier"])
    correlation = _as_opt_str(row["correlation_id"])
    raw = _as_json_obj(row["raw"])
    return OutcomeEvent(
        tenant_id=_as_tenant(row["tenant_id"]),
        id=OutcomeEventId(_as_str(row["id"])),
        name=_as_str(row["name"]),
        signal_class=SignalClass(_as_str(row["signal_class"])),
        value=_as_opt_decimal(row["value"]),
        occurred_at=_as_dt(row["occurred_at"]),
        binding=OutcomeBinding(
            run_id=RunId(bound_run) if bound_run is not None else None,
            tier=BindingTier(bound_tier) if bound_tier is not None else None,
            bound_by=_as_opt_str(row["bound_by"]),
        ),
        entity_keys=_entity_keys_from_json(row["entity_keys"]),
        correlation_id=CorrelationId(correlation) if correlation is not None else None,
        source=_as_str(row["source"]),
        raw=raw,
    )


# --- AttributionResult ------------------------------------------------------------


def attribution_result_to_row(tenant_id: TenantId, model: AttributionResult) -> dict[str, object]:
    """Flatten an :class:`~valuemaxx.core.attribution.AttributionResult` into a row dict."""
    return {
        "outcome_id": model.outcome_id,
        "tenant_id": tenant_id,
        "run_id": model.run_id,
        "tier": model.tier.value if model.tier is not None else None,
        "bound_by": model.bound_by,
        "candidates": [
            {
                "run_id": c.run_id,
                "tier": c.tier.value,
                "score": c.score,
                "rationale": c.rationale,
            }
            for c in model.candidates
        ],
        "review_required": model.review_required,
    }


def row_to_attribution_result(row: Mapping[str, object]) -> AttributionResult:
    """Rebuild an :class:`~valuemaxx.core.attribution.AttributionResult` from a row mapping."""
    run_id = _as_opt_str(row["run_id"])
    tier = _as_opt_str(row["tier"])
    candidates: list[AttributionCandidate] = []
    for raw_item in _as_json_list(row["candidates"]):
        item = _as_json_obj(raw_item)
        candidates.append(
            AttributionCandidate(
                run_id=RunId(_as_str(item["run_id"])),
                tier=BindingTier(_as_str(item["tier"])),
                score=float(_as_number(item["score"])),
                rationale=_as_str(item["rationale"]),
            )
        )
    return AttributionResult(
        tenant_id=_as_tenant(row["tenant_id"]),
        outcome_id=OutcomeEventId(_as_str(row["outcome_id"])),
        run_id=RunId(run_id) if run_id is not None else None,
        tier=BindingTier(tier) if tier is not None else None,
        bound_by=_as_opt_str(row["bound_by"]),
        candidates=tuple(candidates),
        review_required=_as_bool(row["review_required"]),
    )


# --- ReconciliationRecord ---------------------------------------------------------


def reconciliation_record_to_row(
    tenant_id: TenantId, model: ReconciliationRecord
) -> dict[str, object]:
    """Flatten a :class:`~valuemaxx.core.reconciliation.ReconciliationRecord` into a row."""
    provider, project, model_name, token_class, day = model.match_key
    return {
        "id": model.id,
        "tenant_id": tenant_id,
        "match_provider": provider,
        "match_project": project,
        "match_model": model_name,
        "match_token_class": token_class,
        "match_day": day,
        "estimated_total": model.estimated_total,
        "billed_total": model.billed_total,
        "proration_factor": model.proration_factor,
        "drift_pct": model.drift_pct,
        "drift_cause_ranked": list(model.drift_cause_ranked),
        "created_at": model.created_at,
    }


def row_to_reconciliation_record(row: Mapping[str, object]) -> ReconciliationRecord:
    """Rebuild a :class:`~valuemaxx.core.reconciliation.ReconciliationRecord` from a row."""
    return ReconciliationRecord(
        tenant_id=_as_tenant(row["tenant_id"]),
        id=ReconciliationRecordId(_as_str(row["id"])),
        match_key=(
            _as_str(row["match_provider"]),
            _as_str(row["match_project"]),
            _as_str(row["match_model"]),
            _as_str(row["match_token_class"]),
            _as_str(row["match_day"]),
        ),
        estimated_total=_as_decimal(row["estimated_total"]),
        billed_total=_as_decimal(row["billed_total"]),
        proration_factor=_as_decimal(row["proration_factor"]),
        drift_pct=_as_decimal(row["drift_pct"]),
        drift_cause_ranked=_str_tuple_from_json(row["drift_cause_ranked"]),
        created_at=_as_dt(row["created_at"]),
    )


# --- typed row-value coercions ----------------------------------------------------
#
# Row values arrive typed ``object`` from the DBAPI; these narrow each to the exact
# domain type, asserting the stored shape rather than silently coercing a surprise.


def _as_json_obj(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    obj = cast("dict[object, object]", value)
    return {str(k): v for k, v in obj.items()}


def _as_json_list(value: object) -> list[object]:
    assert isinstance(value, list)
    return cast("list[object]", value)


def _as_str(value: object) -> str:
    assert isinstance(value, str)
    return value


def _as_opt_str(value: object) -> str | None:
    if value is None:
        return None
    assert isinstance(value, str)
    return value


def _as_int(value: object) -> int:
    assert isinstance(value, int)
    assert not isinstance(value, bool)
    return value


def _as_bool(value: object) -> bool:
    # Some DBAPIs (SQLite) return 0/1 for booleans; normalise to bool.
    if isinstance(value, bool):
        return value
    assert isinstance(value, int)
    return bool(value)


def _as_number(value: object) -> float | int:
    assert isinstance(value, (int, float))
    assert not isinstance(value, bool)
    return value


def _as_decimal(value: object) -> Decimal:
    from decimal import Decimal as _Decimal

    assert isinstance(value, _Decimal)
    return value


def _as_opt_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    return _as_decimal(value)


def _as_dt(value: object) -> datetime:
    from datetime import datetime as _datetime

    assert isinstance(value, _datetime)
    return value


def _as_opt_dt(value: object) -> datetime | None:
    if value is None:
        return None
    return _as_dt(value)


def _as_tenant(value: object) -> TenantId:
    from uuid import UUID

    from valuemaxx.core.ids import TenantId as _TenantId

    if isinstance(value, UUID):
        return _TenantId(value)
    assert isinstance(value, str)
    return _TenantId(UUID(value))


__all__ = [
    "attribution_result_to_row",
    "cost_event_to_row",
    "outcome_event_to_row",
    "reconciliation_record_to_row",
    "row_to_attribution_result",
    "row_to_cost_event",
    "row_to_outcome_event",
    "row_to_reconciliation_record",
    "row_to_run",
    "run_to_row",
]
