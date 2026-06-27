"""F0-CORE-1c: repository ABCs — tenant_id mandatory first, recon append-only."""

from __future__ import annotations

import inspect
from abc import ABC
from typing import TYPE_CHECKING, cast

import pytest
from valuemaxx.core import repositories as repo

if TYPE_CHECKING:
    from collections.abc import Callable

_ALL_ABCS: tuple[type, ...] = (
    repo.RunRepository,
    repo.CostEventRepository,
    repo.OutcomeEventRepository,
    repo.AttributionResultRepository,
    repo.ReconciliationRepository,
    repo.AllocationRepository,
    repo.RawRecordRepository,
)


def _abstract_methods(cls: type) -> list[str]:
    names: frozenset[str] = getattr(cls, "__abstractmethods__", frozenset())
    return sorted(names)


def _first_param_after_self(cls: type, method_name: str) -> str | None:
    # On an ABC, attribute access yields the plain underlying function (no binding).
    func = cast("Callable[..., object]", getattr(cls, method_name))
    sig = inspect.signature(func)
    params = [name for name in sig.parameters if name != "self"]
    return params[0] if params else None


@pytest.mark.parametrize("abc_cls", _ALL_ABCS)
def test_every_repo_method_tenant_id_first(abc_cls: type) -> None:
    """T-REPO-1: every abstractmethod takes tenant_id: TenantId as first arg after self."""
    for name in _abstract_methods(abc_cls):
        first = _first_param_after_self(abc_cls, name)
        assert first is not None, f"{abc_cls.__name__}.{name} has no parameters"
        assert first == "tenant_id", (
            f"{abc_cls.__name__}.{name} first param is {first!r}, not 'tenant_id'"
        )


def test_reconciliation_repo_is_append_only() -> None:
    """T-REPO-2: the reconciliation repo has no update/mutate/replace method."""
    forbidden = ("update", "mutate", "replace", "delete", "overwrite", "patch")
    methods = set(dir(repo.ReconciliationRepository))
    for m in methods:
        if m.startswith("_"):
            continue
        assert not any(f in m.lower() for f in forbidden), (
            f"ReconciliationRepository.{m} is a mutate path; reconciliation is additive-only"
        )
    # it DOES expose append + list_for_match_key
    recon_methods = _abstract_methods(repo.ReconciliationRepository)
    assert "append" in recon_methods
    assert "list_for_match_key" in recon_methods


def test_outcome_repo_has_retract_and_list_unbound() -> None:
    """T-REPO-3: outcome repo exposes retract (confirmed->retracted) and list_unbound."""
    methods = _abstract_methods(repo.OutcomeEventRepository)
    assert "retract" in methods
    assert "list_unbound" in methods


def test_raw_repo_has_erase_by_entity() -> None:
    """T-REPO-4: raw-record repo exposes erase_by_entity (GDPR/CCPA, H10)."""
    assert "erase_by_entity" in _abstract_methods(repo.RawRecordRepository)


def test_all_seven_abcs_exported() -> None:
    """T-REPO-5: all seven repository ABCs are present and exported."""
    for abc_cls in _ALL_ABCS:
        assert issubclass(abc_cls, ABC)
        assert abc_cls.__name__ in repo.__all__
    assert len(_ALL_ABCS) == 7


def test_abcs_cannot_be_instantiated() -> None:
    """An ABC with abstract methods cannot be instantiated directly."""
    for abc_cls in _ALL_ABCS:
        with pytest.raises(TypeError):
            abc_cls()
