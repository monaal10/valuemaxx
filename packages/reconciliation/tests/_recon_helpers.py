"""In-memory core-ABC stubs for reconciliation tests (no real store, no siblings).

These satisfy the ``valuemaxx.core`` repository ABCs with tenant-scoped dicts so the
reconciliation service can be exercised deterministically without ``valuemaxx.store``
or a real database (real Postgres integration is G5). Only the methods the
reconciliation package calls are implemented with behavior.

Crucially, the in-memory ``ReconciliationRepository`` is append-only (it stores a
flat list and never updates), matching the core ABC — the additive-reconciliation
invariant is structural, not disciplinary.

This is a plain helper module (``_helpers.py``), imported as ``import _recon_helpers`` —
NOT a ``tests`` package and NOT a ``conftest``, so several packages' test suites can
run together without the ``tests.conftest`` plugin-name collision (AGENTS.md §5b).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from typing_extensions import override
from valuemaxx.core import (
    DriftAlert,
    ReconciliationRecord,
    ReconciliationRepository,
    TenantId,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

TENANT_A = TenantId(UUID("00000000-0000-0000-0000-00000000000a"))
TENANT_B = TenantId(UUID("00000000-0000-0000-0000-00000000000b"))


class InMemoryReconciliationRepository(ReconciliationRepository):
    """Tenant-scoped, append-only in-memory :class:`~valuemaxx.core.ReconciliationRepository`.

    Stores records in insertion order and exposes them per match key. There is no
    update/replace path (matching the append-only ABC): a re-reconcile appends a new
    record and the old one is retained for audit.
    """

    def __init__(self) -> None:
        self._records: list[tuple[TenantId, ReconciliationRecord]] = []
        self._drift: dict[TenantId, list[DriftAlert]] = {}

    @override
    def append(self, tenant_id: TenantId, record: ReconciliationRecord) -> None:
        self._records.append((tenant_id, record))

    @override
    def list_for_match_key(
        self, tenant_id: TenantId, match_key: tuple[str, str, str, str, str]
    ) -> Sequence[ReconciliationRecord]:
        return [
            rec
            for tid, rec in self._records
            if tid == tenant_id and rec.match_key == match_key
        ]

    @override
    def list_drift_alerts(self, tenant_id: TenantId) -> Sequence[DriftAlert]:
        return list(self._drift.get(tenant_id, []))

    # --- test helpers (not part of the ABC) ---

    def all_records(self, tenant_id: TenantId) -> list[ReconciliationRecord]:
        """Every appended record for the tenant, in insertion order."""
        return [rec for tid, rec in self._records if tid == tenant_id]

    def record_drift(self, tenant_id: TenantId, alert: DriftAlert) -> None:
        """Seed a drift alert (the service derives these; this is a test convenience)."""
        self._drift.setdefault(tenant_id, []).append(alert)


class FixedClock:
    """A deterministic :class:`~valuemaxx.core.Clock` returning a fixed instant."""

    def __init__(self, instant: datetime) -> None:
        self._instant = instant

    def now(self) -> datetime:
        """Return the fixed instant."""
        return self._instant


class SequentialIds:
    """A deterministic id generator (no ``uuid4()`` in tests)."""

    def __init__(self, prefix: str = "rec") -> None:
        self._prefix = prefix
        self._n = 0

    def __call__(self) -> str:
        """Return the next ``{prefix}-{n}`` id."""
        self._n += 1
        return f"{self._prefix}-{self._n}"


def utc(year: int, month: int, day: int, hour: int = 0) -> datetime:
    """A tz-aware UTC datetime for tests."""
    return datetime(year, month, day, hour, tzinfo=UTC)


__all__ = [
    "TENANT_A",
    "TENANT_B",
    "FixedClock",
    "InMemoryReconciliationRepository",
    "SequentialIds",
    "utc",
]
