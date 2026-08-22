"""Repository ports for continuous optimization stay tenant scoped."""

from __future__ import annotations

import inspect

from valuemaxx.core.optimization_repositories import (
    BaselineRepository,
    DeploymentRepository,
    ExperimentRepository,
    FindingRepository,
    FrontierRepository,
)


def test_every_repository_method_takes_tenant_first() -> None:
    for repository in (
        BaselineRepository,
        DeploymentRepository,
        ExperimentRepository,
        FindingRepository,
        FrontierRepository,
    ):
        for name, method in inspect.getmembers(repository, inspect.isfunction):
            if name.startswith("_"):
                continue
            parameters = tuple(inspect.signature(method).parameters)
            assert parameters[:2] == ("self", "tenant_id")
