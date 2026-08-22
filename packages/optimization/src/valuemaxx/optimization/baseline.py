"""Dominance-based baseline transitions with retained invalidation history."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from valuemaxx.core.optimization import BaselineStatus, ExperimentState

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from datetime import datetime

    from valuemaxx.core.optimization import (
        BaselineCause,
        CallSiteBaseline,
        OptimizationExperiment,
    )

_IN_FLIGHT = frozenset({ExperimentState.PENDING, ExperimentState.RUNNING, ExperimentState.HELD})


@dataclass(frozen=True, slots=True)
class RebaselineResult:
    changed: bool
    superseded: CallSiteBaseline | None
    replacement: CallSiteBaseline | None
    experiments: tuple[OptimizationExperiment, ...]


def rebaseline_if_dominant(
    *,
    current: CallSiteBaseline,
    window_shares: Sequence[Mapping[str, Decimal]],
    experiments: Sequence[OptimizationExperiment],
    cause: BaselineCause,
    now: datetime,
    dominance_threshold: Decimal = Decimal("0.5"),
) -> RebaselineResult:
    """Rebaseline only when one different config dominates every supplied window."""
    if not window_shares:
        return RebaselineResult(False, None, None, tuple(experiments))
    winners: list[tuple[str, Decimal]] = []
    for shares in window_shares:
        if not shares:
            return RebaselineResult(False, None, None, tuple(experiments))
        identity, share = max(shares.items(), key=lambda item: (item[1], item[0]))
        if share <= dominance_threshold:
            return RebaselineResult(False, None, None, tuple(experiments))
        winners.append((identity, share))
    identity = winners[0][0]
    if identity == current.config_identity or any(winner != identity for winner, _ in winners):
        return RebaselineResult(False, None, None, tuple(experiments))

    superseded = current.model_copy(update={"status": BaselineStatus.SUPERSEDED})
    material = f"{current.call_site_id}:{identity}:{now.isoformat()}"
    from valuemaxx.core.optimization import CallSiteBaseline

    replacement = CallSiteBaseline(
        tenant_id=current.tenant_id,
        id=f"baseline-{hashlib.sha256(material.encode()).hexdigest()}",
        call_site_id=current.call_site_id,
        config_identity=identity,
        status=BaselineStatus.BURN_IN,
        dominant_share=min(share for _, share in winners),
        outcome_rate=None,
        cause=cause,
        activated_at=now,
    )
    reason = f"baseline {current.id} superseded by dominant config {identity}"
    updated = tuple(
        experiment.model_copy(
            update={"state": ExperimentState.INVALIDATED, "invalidation_reason": reason}
        )
        if experiment.baseline_id == current.id and experiment.state in _IN_FLIGHT
        else experiment
        for experiment in experiments
    )
    return RebaselineResult(True, superseded, replacement, updated)


__all__ = ["RebaselineResult", "rebaseline_if_dominant"]
