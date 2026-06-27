"""Test fixtures for the allocation suite (no real store, no siblings).

Plain helper module (``_helpers.py``), imported as ``import _alloc_helpers`` — NOT a
``tests`` package and NOT a ``conftest``, so several packages' suites run together
without the ``tests.conftest`` plugin-name collision (AGENTS.md §5b).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from typing_extensions import override
from valuemaxx.core import (
    AllocatedLine,
    AllocatedRollup,
    AllocationRepository,
    AttemptId,
    CaptureGranularity,
    CostEvent,
    CostEventId,
    Provenance,
    ProvenanceLabel,
    RunId,
    TenantId,
    TokenVector,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from decimal import Decimal

TENANT_A = TenantId(UUID("00000000-0000-0000-0000-0000000000a1"))
TENANT_B = TenantId(UUID("00000000-0000-0000-0000-0000000000b2"))

_TOKENS = TokenVector(
    input_uncached=100,
    cache_read=0,
    cache_write_5m=0,
    cache_write_1h=0,
    output=50,
    reasoning=0,
)


def make_cost_event(
    *,
    event_id: str,
    cost_usd: Decimal | None,
    tenant_id: TenantId = TENANT_A,
    run_id: str = "run-1",
    provider: str = "anthropic",
    model: str = "claude-sonnet-4",
) -> CostEvent:
    """Build a measured :class:`~valuemaxx.core.CostEvent` for allocation tests."""
    return CostEvent(
        tenant_id=tenant_id,
        id=CostEventId(event_id),
        run_id=RunId(run_id),
        attempt_id=AttemptId(event_id),  # one attempt per event in these tests
        provider=provider,
        model=model,
        tokens=_TOKENS,
        capture_granularity=CaptureGranularity.PER_ATTEMPT,
        provenance=ProvenanceLabel(provenance=Provenance.MEASURED),
        cost_usd=cost_usd,
        is_streaming=False,
        partial_recovered=False,
        billing_uncertain_abort=cost_usd is None,
        provenance_warnings=(),
        occurred_at=datetime(2026, 6, 27, 12, tzinfo=UTC),
    )


class InMemoryAllocationRepository(AllocationRepository):
    """Tenant-scoped in-memory :class:`~valuemaxx.core.AllocationRepository`."""

    def __init__(self) -> None:
        self._lines: dict[tuple[TenantId, RunId], tuple[AllocatedLine, ...]] = {}
        self._rollups: dict[tuple[TenantId, RunId], AllocatedRollup] = {}

    @override
    def upsert_lines(self, tenant_id: TenantId, run_id: RunId, lines: Sequence[object]) -> None:
        typed = tuple(line for line in lines if isinstance(line, AllocatedLine))
        self._lines[(tenant_id, run_id)] = typed

    @override
    def list_for_run(self, tenant_id: TenantId, run_id: RunId) -> Sequence[object]:
        return list(self._lines.get((tenant_id, run_id), ()))

    @override
    def get_rollup(self, tenant_id: TenantId, run_id: RunId) -> AllocatedRollup | None:
        return self._rollups.get((tenant_id, run_id))

    # --- test helper (not part of the ABC) ---

    def put_rollup(self, tenant_id: TenantId, run_id: RunId, rollup: AllocatedRollup) -> None:
        """Seed a rollup so ``get_rollup`` returns it (the service writes these)."""
        self._rollups[(tenant_id, run_id)] = rollup


__all__ = [
    "TENANT_A",
    "TENANT_B",
    "InMemoryAllocationRepository",
    "make_cost_event",
]
