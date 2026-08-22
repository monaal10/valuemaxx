"""Tenant-scoped persistence ports for continuous optimization artifacts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from valuemaxx.core.ids import TenantId
    from valuemaxx.core.optimization import (
        CallSiteBaseline,
        FrontierEntry,
        LinterFinding,
        OptimizationDeployment,
        OptimizationExperiment,
    )


class BaselineRepository(ABC):
    """Retained baseline history for discovered call sites."""

    @abstractmethod
    def upsert(self, tenant_id: TenantId, baseline: CallSiteBaseline) -> None:
        """Persist a baseline without deleting superseded history."""

    @abstractmethod
    def list_for_call_site(
        self, tenant_id: TenantId, call_site_id: str
    ) -> Sequence[CallSiteBaseline]:
        """List all baseline generations for one call site."""


class FindingRepository(ABC):
    """Persistence for structural linter findings."""

    @abstractmethod
    def upsert(self, tenant_id: TenantId, finding: LinterFinding) -> None:
        """Persist an idempotent structural finding."""

    @abstractmethod
    def list_for_call_site(self, tenant_id: TenantId, call_site_id: str) -> Sequence[LinterFinding]:
        """List structural findings for one call site."""


class FrontierRepository(ABC):
    """Persistence for the current evidence frontier."""

    @abstractmethod
    def replace_for_call_site(
        self, tenant_id: TenantId, call_site_id: str, entries: Sequence[FrontierEntry]
    ) -> None:
        """Replace the projected frontier while historical experiments remain retained."""

    @abstractmethod
    def list_for_call_site(self, tenant_id: TenantId, call_site_id: str) -> Sequence[FrontierEntry]:
        """List frontier rows for one call site."""


class ExperimentRepository(ABC):
    """Persistence enforcing one active experiment per call site."""

    @abstractmethod
    def upsert(self, tenant_id: TenantId, experiment: OptimizationExperiment) -> None:
        """Persist an experiment state transition."""

    @abstractmethod
    def list_for_call_site(
        self, tenant_id: TenantId, call_site_id: str
    ) -> Sequence[OptimizationExperiment]:
        """List retained experiment history for one call site."""


class DeploymentRepository(ABC):
    """Persistence for separately authorized production deployments."""

    @abstractmethod
    def upsert(self, tenant_id: TenantId, deployment: OptimizationDeployment) -> None:
        """Persist a deployment or kill-switch transition."""

    @abstractmethod
    def get_active(self, tenant_id: TenantId, call_site_id: str) -> OptimizationDeployment | None:
        """Return the active deployment for a call site, if any."""


__all__ = [
    "BaselineRepository",
    "DeploymentRepository",
    "ExperimentRepository",
    "FindingRepository",
    "FrontierRepository",
]
