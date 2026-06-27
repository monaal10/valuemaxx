"""F0-CORE-1a: StrictModel + TenantScopedModel — frozen/forbid/strict + tenancy.

These bases are load-bearing: every domain model inherits frozen+extra=forbid+
strict, and every event additionally requires a non-nullable tenant_id and
rejects naive datetimes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from atm_core.base import StrictModel, TenantScopedModel
from atm_core.ids import TenantId
from pydantic import ValidationError


class _Sample(StrictModel):
    name: str
    count: int


class _Event(TenantScopedModel):
    label: str
    occurred_at: datetime


def _tenant() -> TenantId:
    return TenantId(uuid4())


def test_frozen_mutation_raises() -> None:
    """T-BASE-3a: instances are immutable; assignment raises."""
    m = _Sample(name="a", count=1)
    with pytest.raises(ValidationError):
        m.name = "b"  # pydantic frozen=True raises at runtime on assignment


def test_extra_forbidden_raises() -> None:
    """T-BASE-3b: unexpected fields are rejected (extra='forbid')."""
    with pytest.raises(ValidationError):
        _Sample(name="a", count=1, extra_field="nope")  # type: ignore[call-arg]


def test_strict_no_coercion() -> None:
    """T-BASE-3c: strict mode — '5' is NOT coerced to int 5."""
    with pytest.raises(ValidationError):
        _Sample(name="a", count="5")  # type: ignore[arg-type]


def test_tenant_required() -> None:
    """T-BASE-1: an untenanted event cannot be constructed."""
    with pytest.raises(ValidationError):
        _Event(label="x", occurred_at=datetime.now(tz=UTC))  # type: ignore[call-arg]


def test_tenant_cannot_be_none() -> None:
    """T-BASE-1b: tenant_id is non-nullable — None is rejected."""
    with pytest.raises(ValidationError):
        _Event(
            tenant_id=None,  # type: ignore[arg-type]
            label="x",
            occurred_at=datetime.now(tz=UTC),
        )


def test_tenant_scoped_construction_succeeds() -> None:
    """A properly tenanted, tz-aware event constructs cleanly."""
    ev = _Event(tenant_id=_tenant(), label="x", occurred_at=datetime.now(tz=UTC))
    assert ev.label == "x"


def test_naive_datetime_rejected() -> None:
    """T-BASE-2: a naive datetime (no tzinfo) is rejected — UTC must be explicit."""
    with pytest.raises(ValidationError):
        _Event(
            tenant_id=_tenant(),
            label="x",
            occurred_at=datetime(2026, 1, 1, 12, 0, 0),
        )


def test_aware_datetime_accepted() -> None:
    ev = _Event(
        tenant_id=_tenant(),
        label="x",
        occurred_at=datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
    )
    assert ev.occurred_at.tzinfo is not None


def test_strict_model_is_pydantic_frozen_config() -> None:
    """The base config is frozen, forbids extras, and is strict."""
    cfg = StrictModel.model_config
    assert cfg.get("frozen") is True
    assert cfg.get("extra") == "forbid"
    assert cfg.get("strict") is True


def test_tenant_scoped_inherits_strict_config() -> None:
    cfg = TenantScopedModel.model_config
    assert cfg.get("frozen") is True
    assert cfg.get("extra") == "forbid"
    assert cfg.get("strict") is True
