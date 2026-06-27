"""In-memory core-ABC stubs for attribution tests (no real store, no siblings).

These satisfy the ``valuemaxx.core`` repository/queue ABCs with simple, tenant-scoped
dicts so the cascade can be exercised deterministically without ``valuemaxx.store``
or a real database. Only the methods the attribution package calls are exercised;
the rest raise to make accidental use obvious.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from typing_extensions import override
from valuemaxx.core import (
    OutcomeEventId,
    Run,
    RunId,
    RunRepository,
    TenantId,
)
from valuemaxx.core.repositories import ReviewQueue

if TYPE_CHECKING:
    from collections.abc import Sequence

TENANT_A = TenantId(UUID("00000000-0000-0000-0000-00000000000a"))
TENANT_B = TenantId(UUID("00000000-0000-0000-0000-00000000000b"))


def make_run(
    *,
    run_id: str,
    tenant_id: TenantId = TENANT_A,
    started_at: datetime,
    entity_keys: frozenset[tuple[str, str]] = frozenset(),
    ended_at: datetime | None = None,
) -> Run:
    """Build a :class:`~valuemaxx.core.Run` for tests."""
    return Run(
        tenant_id=tenant_id,
        id=RunId(run_id),
        agent_name="test-agent",
        started_at=started_at,
        ended_at=ended_at,
        entity_keys=entity_keys,
    )


class InMemoryRunRepository(RunRepository):
    """Tenant-scoped in-memory :class:`~valuemaxx.core.RunRepository`."""

    def __init__(self) -> None:
        self._runs: dict[tuple[TenantId, RunId], Run] = {}

    @override
    def upsert(self, tenant_id: TenantId, run: Run) -> None:
        self._runs[(tenant_id, run.id)] = run

    @override
    def get(self, tenant_id: TenantId, run_id: RunId) -> Run | None:
        return self._runs.get((tenant_id, run_id))

    @override
    def list_by_entity(self, tenant_id: TenantId, entity_key: tuple[str, str]) -> Sequence[Run]:
        return [
            run
            for (tid, _rid), run in self._runs.items()
            if tid == tenant_id and entity_key in run.entity_keys
        ]


class InMemoryReviewQueue(ReviewQueue):
    """Tenant-scoped in-memory :class:`~valuemaxx.core.ReviewQueue`."""

    def __init__(self) -> None:
        self._items: dict[TenantId, list[object]] = {}

    @override
    def enqueue(self, tenant_id: TenantId, item: object) -> None:
        self._items.setdefault(tenant_id, []).append(item)

    @override
    def list_pending(self, tenant_id: TenantId) -> Sequence[object]:
        return list(self._items.get(tenant_id, []))


class FixedClock:
    """A deterministic :class:`~valuemaxx.core.Clock` returning a fixed instant."""

    def __init__(self, instant: datetime) -> None:
        self._instant = instant

    def now(self) -> datetime:
        return self._instant


class StubLlmJudge:
    """A deterministic :class:`~valuemaxx.core.LlmJudge` returning a preset score."""

    def __init__(self, score: float) -> None:
        self._score = score
        self.calls: list[tuple[str, str, str]] = []

    def grade(self, *, prediction: str, reference: str, rubric: str) -> float:
        self.calls.append((prediction, reference, rubric))
        return self._score


def utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    """A tz-aware UTC datetime for tests."""
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


__all__ = [
    "TENANT_A",
    "TENANT_B",
    "FixedClock",
    "InMemoryReviewQueue",
    "InMemoryRunRepository",
    "OutcomeEventId",
    "StubLlmJudge",
    "make_run",
    "utc",
]
