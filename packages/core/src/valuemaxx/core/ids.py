"""Typed identifiers — distinct ``NewType`` aliases so ids can't be transposed.

``TenantId`` wraps a :class:`~uuid.UUID` (tenancy is identified by UUID, §3.2);
the remaining identifiers are opaque string :func:`~typing.NewType` aliases so a
``RunId`` can never be silently passed where a ``CostEventId`` is expected.
"""

from __future__ import annotations

from typing import NewType
from uuid import UUID

TenantId = NewType("TenantId", UUID)
"""A customer account's isolation key (required, non-nullable, §3.2)."""

RunId = NewType("RunId", str)
"""Identifies one agent run (the join key for cost and outcome)."""

CostEventId = NewType("CostEventId", str)
"""Identifies one CostEvent (one HTTP attempt where the mechanism allows, §5.2)."""

OutcomeEventId = NewType("OutcomeEventId", str)
"""Identifies one OutcomeEvent."""

AttributionId = NewType("AttributionId", str)
"""Identifies one AttributionResult."""

ReconciliationRecordId = NewType("ReconciliationRecordId", str)
"""Identifies one additive ReconciliationRecord (§5.3)."""

AttemptId = NewType("AttemptId", str)
"""Identifies one HTTP attempt within a run (part of the CostEvent dedup key)."""

CorrelationId = NewType("CorrelationId", str)
"""A round-tripped id used to deterministically bind delayed outcomes (T3, §6.3)."""


__all__ = [
    "AttemptId",
    "AttributionId",
    "CorrelationId",
    "CostEventId",
    "OutcomeEventId",
    "ReconciliationRecordId",
    "RunId",
    "TenantId",
]
