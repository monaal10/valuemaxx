"""The Run — one agent-run boundary, the join key for cost and outcome (§6)."""

from __future__ import annotations

from datetime import datetime

from atm_core.base import TenantScopedModel
from atm_core.ids import RunId


class Run(TenantScopedModel):
    """An agent run: the unit that accumulates cost and to which outcomes bind."""

    id: RunId
    agent_name: str | None
    started_at: datetime
    ended_at: datetime | None
    entity_keys: frozenset[tuple[str, str]]


__all__ = ["Run"]
