"""F0-CORE-1a: typed id NewTypes — TenantId is a UUID NewType, the rest are str."""

from __future__ import annotations

from uuid import UUID, uuid4

from atm_core import ids


def test_tenant_id_is_uuid_newtype() -> None:
    """TenantId wraps a UUID (tenancy is identified by UUID, §3.2)."""
    raw = uuid4()
    tid = ids.TenantId(raw)
    assert isinstance(tid, UUID)
    assert tid == raw


def test_string_ids_are_str_newtypes() -> None:
    """The event/correlation ids are opaque string NewTypes."""
    for ctor in (
        ids.RunId,
        ids.CostEventId,
        ids.OutcomeEventId,
        ids.AttributionId,
        ids.ReconciliationRecordId,
        ids.AttemptId,
        ids.CorrelationId,
    ):
        value = ctor("abc-123")
        assert isinstance(value, str)
        assert value == "abc-123"


def test_all_id_types_exported() -> None:
    """Every id type is exported from atm_core.ids."""
    expected = {
        "TenantId",
        "RunId",
        "CostEventId",
        "OutcomeEventId",
        "AttributionId",
        "ReconciliationRecordId",
        "AttemptId",
        "CorrelationId",
    }
    assert expected <= set(ids.__all__)
