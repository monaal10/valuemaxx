"""F0-CORE-1b: Run — the agent-run record (the join key)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from atm_core.ids import RunId, TenantId
from atm_core.run import Run
from pydantic import ValidationError


def _tenant() -> TenantId:
    return TenantId(uuid4())


def test_run_minimal() -> None:
    run = Run(
        tenant_id=_tenant(),
        id=RunId("run-1"),
        agent_name=None,
        started_at=datetime.now(tz=UTC),
        ended_at=None,
        entity_keys=frozenset(),
    )
    assert run.id == RunId("run-1")
    assert run.ended_at is None


def test_run_with_entity_keys() -> None:
    run = Run(
        tenant_id=_tenant(),
        id=RunId("run-2"),
        agent_name="sdr-agent",
        started_at=datetime.now(tz=UTC),
        ended_at=datetime.now(tz=UTC),
        entity_keys=frozenset({("customer_id", "c-9")}),
    )
    assert ("customer_id", "c-9") in run.entity_keys


def test_run_requires_tenant() -> None:
    with pytest.raises(ValidationError):
        Run(  # type: ignore[call-arg]
            id=RunId("run-1"),
            agent_name=None,
            started_at=datetime.now(tz=UTC),
            ended_at=None,
            entity_keys=frozenset(),
        )
