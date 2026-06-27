"""Eval repository ABCs — tenant_id first (§3.2)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from valuemaxx.core.eval.models import EvalDataset, EvalRecommendation
    from valuemaxx.core.ids import TenantId


class EvalDatasetRepository(ABC):
    """Persistence for versioned eval datasets."""

    @abstractmethod
    def upsert(self, tenant_id: TenantId, dataset: EvalDataset) -> None:
        """Insert or update an eval dataset (idempotent on id+version)."""

    @abstractmethod
    def get(self, tenant_id: TenantId, dataset_id: str) -> EvalDataset | None:
        """Fetch the latest version of a dataset by id, or None."""


class EvalRecommendationRepository(ABC):
    """Persistence for eval recommendations."""

    @abstractmethod
    def upsert(self, tenant_id: TenantId, recommendation: EvalRecommendation) -> None:
        """Insert or update a recommendation."""

    @abstractmethod
    def list_for_incumbent(
        self, tenant_id: TenantId, incumbent_model: str
    ) -> Sequence[EvalRecommendation]:
        """List recommendations evaluated against an incumbent model."""


__all__ = ["EvalDatasetRepository", "EvalRecommendationRepository"]
