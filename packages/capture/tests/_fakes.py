"""Shared in-memory test doubles for capture tests (no real store; AGENTS.md §1).

These are true boundary fakes — the repository ABC under
:class:`~valuemaxx.core.repositories.CostEventRepository` — never the thing under
test. Defined once here so every capture test module reuses them (no duplication).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import uuid4

from typing_extensions import override
from valuemaxx.core.cost import CostEvent
from valuemaxx.core.enums import CaptureGranularity, Provenance
from valuemaxx.core.ids import AttemptId, CostEventId, RunId, TenantId
from valuemaxx.core.provenance import ProvenanceLabel
from valuemaxx.core.repositories import CostEventRepository
from valuemaxx.core.tokens import TokenVector

if TYPE_CHECKING:
    from collections.abc import Sequence

TEST_TENANT = TenantId(uuid4())


def make_cost_event(n: int, *, tenant_id: TenantId = TEST_TENANT) -> CostEvent:
    """Build a minimal, valid CostEvent for tests (measured, non-streaming)."""
    return CostEvent(
        tenant_id=tenant_id,
        id=CostEventId(f"ce-{n}"),
        run_id=RunId(f"run-{n}"),
        attempt_id=AttemptId(f"att-{n}"),
        provider="anthropic",
        model="claude-opus-4-8",
        tokens=TokenVector(
            input_uncached=10,
            cache_read=0,
            cache_write_5m=0,
            cache_write_1h=0,
            output=5,
            reasoning=0,
        ),
        capture_granularity=CaptureGranularity.PER_ATTEMPT,
        provenance=ProvenanceLabel(provenance=Provenance.MEASURED),
        cost_usd=Decimal("0.000150"),
        is_streaming=False,
        partial_recovered=False,
        billing_uncertain_abort=False,
        provenance_warnings=(),
        occurred_at=datetime(2026, 6, 27, tzinfo=UTC),
    )


class RecordingCostRepo(CostEventRepository):
    """An in-memory cost-event repo that records every upsert in order."""

    def __init__(self) -> None:
        self.upserted: list[CostEvent] = []

    @override
    def upsert(self, tenant_id: TenantId, event: CostEvent) -> None:
        self.upserted.append(event)

    @override
    def list_for_run(self, tenant_id: TenantId, run_id: RunId) -> Sequence[CostEvent]:
        return tuple(e for e in self.upserted if e.run_id == run_id)

    @override
    def list_in_window(
        self, tenant_id: TenantId, start: datetime, end: datetime
    ) -> Sequence[CostEvent]:
        return tuple(e for e in self.upserted if start <= e.occurred_at < end)


class ThrowingCostRepo(CostEventRepository):
    """A cost-event repo whose upsert always raises (drives the fail-open drain path)."""

    @override
    def upsert(self, tenant_id: TenantId, event: CostEvent) -> None:
        raise RuntimeError("store unavailable")

    @override
    def list_for_run(self, tenant_id: TenantId, run_id: RunId) -> Sequence[CostEvent]:
        return ()

    @override
    def list_in_window(
        self, tenant_id: TenantId, start: datetime, end: datetime
    ) -> Sequence[CostEvent]:
        return ()


__all__ = ["TEST_TENANT", "RecordingCostRepo", "ThrowingCostRepo", "make_cost_event"]
