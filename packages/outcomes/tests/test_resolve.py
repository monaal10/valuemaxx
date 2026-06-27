"""Symbol resolution for wrapt targets (function rules + run_id injection)."""

from __future__ import annotations

import sys
import types
from typing import TYPE_CHECKING

import pytest
from valuemaxx.outcomes.instrument._resolve import resolve_target

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def host_pkg() -> Iterator[types.ModuleType]:
    mod = types.ModuleType("hostpkg_resolve")

    class PaymentIntent:
        @staticmethod
        def create() -> None:  # pragma: no cover - not called, only resolved
            return None

    def top_level() -> None:  # pragma: no cover - not called, only resolved
        return None

    mod.PaymentIntent = PaymentIntent  # type: ignore[attr-defined]
    mod.top_level = top_level  # type: ignore[attr-defined]
    sys.modules["hostpkg_resolve"] = mod
    yield mod
    sys.modules.pop("hostpkg_resolve", None)


def test_resolve_module_level_function(host_pkg: types.ModuleType) -> None:
    """A module.function target resolves to (module, function)."""
    resolved = resolve_target("hostpkg_resolve.top_level")
    assert resolved is not None
    assert resolved.module_name == "hostpkg_resolve"
    assert resolved.attr_path == "top_level"


def test_resolve_class_method(host_pkg: types.ModuleType) -> None:
    """A module.Class.method target keeps Class.method as the attr path."""
    resolved = resolve_target("hostpkg_resolve.PaymentIntent.create")
    assert resolved is not None
    assert resolved.module_name == "hostpkg_resolve"
    assert resolved.attr_path == "PaymentIntent.create"


def test_resolve_single_segment_is_unresolvable() -> None:
    """A bare single-segment name cannot be a patch target."""
    assert resolve_target("justaname") is None


def test_resolve_missing_attribute_is_unresolvable(host_pkg: types.ModuleType) -> None:
    """An importable module without the named attribute is unresolved (not a crash)."""
    assert resolve_target("hostpkg_resolve.nonexistent_attr") is None


def test_resolve_unimportable_module_is_unresolvable() -> None:
    """A target whose module never imports is unresolved."""
    assert resolve_target("totally.not.a.module.func") is None
