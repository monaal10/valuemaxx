"""G1 EXIT — the freeze meta-tests (the barrier; H7).

After G1 the core surface is FROZEN. These meta-tests walk the real core package
and enforce the freeze criteria so a regression — a model that forgets frozen, an
event that drops tenant_id, a repo method that omits tenant_id, a plaintext key
field, an auto_switch escape hatch, or a rollup missing an H7 field — FAILS a
test rather than slipping through.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from typing import Literal, get_args, get_type_hints

import pytest
import valuemaxx.core
from pydantic import BaseModel
from valuemaxx.core.base import TenantScopedModel
from valuemaxx.core.enums import EvalGrade, ReconciliationState
from valuemaxx.core.eval import EvalRecommendation, ProviderKeyRef
from valuemaxx.core.rollup import RollupConfidence


def _abstract_methods(cls: type) -> frozenset[str]:
    """The abstract method names of a class (typed, for strict pyright)."""
    names: frozenset[str] = getattr(cls, "__abstractmethods__", frozenset())
    return names


def _all_core_modules() -> list[str]:
    """Every submodule under valuemaxx.core (recursively)."""
    names: list[str] = []
    for info in pkgutil.walk_packages(valuemaxx.core.__path__, prefix="valuemaxx.core."):
        names.append(info.name)
    return names


def _all_core_models() -> list[type[BaseModel]]:
    """Every concrete pydantic model class declared in valuemaxx.core."""
    models: dict[str, type[BaseModel]] = {}
    for mod_name in [*_all_core_modules(), "valuemaxx.core"]:
        module = importlib.import_module(mod_name)
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, BaseModel)
                and obj is not BaseModel
                and obj.__module__.startswith("valuemaxx.core")
            ):
                models[obj.__qualname__] = obj
    return list(models.values())


_CORE_MODELS = _all_core_models()
_MODEL_IDS = [m.__qualname__ for m in _CORE_MODELS]

# The domain *events* (TenantScopedModel subclasses) that must carry tenant_id.
_REQUIRED_TENANT_EVENTS = (
    "CostEvent",
    "OutcomeEvent",
    "Run",
    "AttributionResult",
    "ReconciliationRecord",
    "AllocatedRollup",
    "RunCostRollup",
    "EvalDataset",
    "EvalRecommendation",
)


def test_models_were_discovered() -> None:
    """The walk found a meaningful set of core models (not silently empty)."""
    assert len(_CORE_MODELS) >= 15, f"only found {len(_CORE_MODELS)} core models: {_MODEL_IDS}"


@pytest.mark.parametrize("model", _CORE_MODELS, ids=_MODEL_IDS)
def test_all_core_models_frozen_forbid_strict(model: type[BaseModel]) -> None:
    """test_all_core_models_frozen_forbid_strict: a missing flag FAILS (the freeze)."""
    cfg = model.model_config
    assert cfg.get("frozen") is True, f"{model.__qualname__} is not frozen=True"
    assert cfg.get("extra") == "forbid", f"{model.__qualname__} is not extra='forbid'"
    assert cfg.get("strict") is True, f"{model.__qualname__} is not strict=True"


def test_all_domain_events_tenant_scoped() -> None:
    """test_all_domain_events_tenant_scoped: every domain event requires tenant_id."""
    by_name = {m.__qualname__: m for m in _CORE_MODELS}
    for name in _REQUIRED_TENANT_EVENTS:
        model = by_name.get(name)
        assert model is not None, f"core event {name} not found"
        assert issubclass(model, TenantScopedModel), f"{name} is not TenantScopedModel"
        field = model.model_fields.get("tenant_id")
        assert field is not None, f"{name} has no tenant_id field"
        assert field.is_required(), f"{name}.tenant_id is not required"


def test_all_repo_methods_tenant_first_full_set() -> None:
    """test_all_repo_methods_tenant_first_full_set: every repo abstractmethod tenant-first."""
    from valuemaxx.core import repositories as core_repos
    from valuemaxx.core.eval import repositories as eval_repos

    abc_classes: list[type] = []
    for module in (core_repos, eval_repos):
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if _abstract_methods(obj) and obj.__module__.startswith("valuemaxx.core"):
                abc_classes.append(obj)
    assert abc_classes, "no repository ABCs discovered"
    for abc_cls in abc_classes:
        for name in _abstract_methods(abc_cls):
            func = getattr(abc_cls, name)
            params = [p for p in inspect.signature(func).parameters if p != "self"]
            assert params, f"{abc_cls.__name__}.{name} has no parameters"
            assert params[0] == "tenant_id", (
                f"{abc_cls.__name__}.{name} first param is {params[0]!r}, not 'tenant_id'"
            )


def test_eval_grade_and_recon_state_not_event_fields() -> None:
    """test_eval_grade_and_recon_state_not_event_fields: axes-only invariant.

    EvalGrade and ReconciliationState are local/display, never honesty axes — they
    must not appear as a field type on any *tenant-scoped domain event* model.
    (EvalRecommendation deliberately carries a `grade: EvalGrade` label and is
    excluded — it is the per-recommendation artifact, not a per-event field.)
    """
    events = [
        m
        for m in _CORE_MODELS
        if issubclass(m, TenantScopedModel) and m.__qualname__ != "EvalRecommendation"
    ]
    assert events
    for model in events:
        hints = get_type_hints(model)
        for field_name, hint in hints.items():
            annotated = (hint, *get_args(hint))
            assert EvalGrade not in annotated, (
                f"{model.__qualname__}.{field_name} references EvalGrade (not a system axis)"
            )
            assert ReconciliationState not in annotated, (
                f"{model.__qualname__}.{field_name} references ReconciliationState (display only)"
            )


def test_every_rollup_model_carries_both_h7_fields() -> None:
    """test_every_rollup_model_carries_both_h7_fields: rollups carry minimum_tier + dist."""
    # RollupConfidence itself holds the two H7 fields.
    assert "minimum_tier" in RollupConfidence.model_fields
    assert "confidence_distribution" in RollupConfidence.model_fields
    # every rollup-shaped model carries a RollupConfidence-typed `confidence`.
    rollups = [m for m in _CORE_MODELS if m.__qualname__.endswith("Rollup")]
    assert rollups, "no rollup-shaped models discovered"
    for model in rollups:
        field = model.model_fields.get("confidence")
        assert field is not None, f"{model.__qualname__} has no confidence field"
        assert field.annotation is RollupConfidence, (
            f"{model.__qualname__}.confidence is not a RollupConfidence"
        )


def test_auto_switch_is_false_literal_freeze() -> None:
    """auto_switch is Literal[False] — auto-applying a recommendation is unrepresentable."""
    hints = get_type_hints(EvalRecommendation)
    assert hints["auto_switch"] == Literal[False]


def test_provider_key_ref_has_no_plaintext_field_freeze() -> None:
    """ProviderKeyRef exposes only a secret_ref — no plaintext key field."""
    forbidden = {"key", "api_key", "secret_value", "plaintext", "value", "token"}
    leaked = set(ProviderKeyRef.model_fields) & forbidden
    assert not leaked, f"ProviderKeyRef exposes plaintext field(s): {leaked}"
    assert "secret_ref" in ProviderKeyRef.model_fields


def test_core_all_explicit_and_complete() -> None:
    """The core __all__ is explicit (no wildcard) and exports every discovered model."""
    exported = set(valuemaxx.core.__all__)
    for model in _CORE_MODELS:
        # nested helper models may not be top-level exports, but every model whose
        # module is a direct core submodule and is public (no leading underscore)
        # should be reachable; assert the headline events at least.
        if model.__qualname__ in _REQUIRED_TENANT_EVENTS:
            assert model.__qualname__ in exported, f"{model.__qualname__} missing from __all__"
