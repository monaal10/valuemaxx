"""F0-CORE-1b: ReconciliationRecord — additive, never an UPDATE to the estimate."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from atm_core.ids import ReconciliationRecordId, TenantId
from atm_core.reconciliation import ReconciliationRecord


def _tenant() -> TenantId:
    return TenantId(uuid4())


def _record(**overrides: object) -> ReconciliationRecord:
    base: dict[str, object] = {
        "tenant_id": _tenant(),
        "id": ReconciliationRecordId("rec-1"),
        "match_key": ("anthropic", "proj-1", "claude-opus-4-8", "output", "2026-06-27"),
        "estimated_total": Decimal("100.00"),
        "billed_total": Decimal("103.50"),
        "proration_factor": Decimal("1.035"),
        "drift_pct": Decimal("3.50"),
        "drift_cause_ranked": ("cache_mispricing", "negotiated_rate"),
        "created_at": datetime.now(tz=UTC),
    }
    base.update(overrides)
    return ReconciliationRecord(**base)  # type: ignore[arg-type]


def test_match_key_is_five_tuple() -> None:
    """T-RR-2: match_key = (provider, project, model, token_class, day)."""
    rec = _record()
    assert rec.match_key == (
        "anthropic",
        "proj-1",
        "claude-opus-4-8",
        "output",
        "2026-06-27",
    )


def test_proration_and_drift_present() -> None:
    rec = _record()
    assert rec.proration_factor == Decimal("1.035")
    assert rec.drift_pct == Decimal("3.50")
    assert rec.drift_cause_ranked[0] == "cache_mispricing"


def test_reconciliation_record_is_additive_no_mutate_field() -> None:
    """T-RR-1: AST scan — no field points back to mutate an estimate (additive only)."""
    forbidden_substrings = ("update", "mutate", "replace", "overwrite", "patch")
    for field_name in ReconciliationRecord.model_fields:
        lowered = field_name.lower()
        assert not any(sub in lowered for sub in forbidden_substrings), (
            f"ReconciliationRecord field {field_name!r} suggests a mutate-estimate path"
        )
