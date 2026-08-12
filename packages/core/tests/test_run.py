"""F0-CORE-1b: Run — the agent-run record (the join key)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError
from valuemaxx.core.ids import RunId, TenantId
from valuemaxx.core.run import Run


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


def test_run_carries_experiment_variant_and_app() -> None:
    """Recorded on the run so a comparison over history is possible later.

    No engine reads these yet. They are here because they are the one class of field
    that cannot be added retroactively: traffic that ran without a variant stamp can
    never be split into arms afterwards, so the fields must exist before the history
    they describe is made. All three default to None — most traffic is not an
    experiment, and pretending otherwise would invent arms.
    """

    def build(**extra: object) -> Run:
        return Run(
            tenant_id=_tenant(),
            id=RunId("run-x"),
            agent_name=None,
            started_at=datetime.now(tz=UTC),
            ended_at=None,
            entity_keys=frozenset(),
            **extra,  # pyright: ignore[reportArgumentType]
        )

    run = build(experiment="haiku-vs-opus", variant="haiku", app="support")
    assert run.experiment == "haiku-vs-opus"
    assert run.variant == "haiku"
    assert run.app == "support"

    plain = build()
    assert plain.experiment is None
    assert plain.variant is None
    assert plain.app is None
