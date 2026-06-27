"""F0-CAPS: Registry register/all/for_surface + push registration discovery."""

from __future__ import annotations

import sys
import types

import pytest
from pydantic import BaseModel
from valuemaxx.capabilities.decorator import CapabilitySpec, capability
from valuemaxx.capabilities.discovery import discover_and_register
from valuemaxx.capabilities.errors import DuplicateCapabilityError, MissingRegisterError
from valuemaxx.capabilities.registry import Registry
from valuemaxx.capabilities.surfaces import Mode, Surface


class _In(BaseModel):
    x: int


class _Out(BaseModel):
    y: int


def _handler(payload: _In) -> _Out:
    return _Out(y=payload.x)


def _spec(name: str, surfaces: Surface = Surface.API) -> CapabilitySpec[_In, _Out]:
    return capability(
        name=name,
        input_model=_In,
        output_model=_Out,
        handler=_handler,
        description="d",
        surfaces=surfaces,
        mode=Mode.REQUEST_RESPONSE,
    )


def test_register_and_all() -> None:
    reg = Registry()
    reg.register(_spec("a"))
    reg.register(_spec("b"))
    assert {c.name for c in reg.all()} == {"a", "b"}


def test_duplicate_name_is_hard_error() -> None:
    """T-REG-1: registering a duplicate name raises (HARD, no silent overwrite)."""
    reg = Registry()
    reg.register(_spec("a"))
    with pytest.raises(DuplicateCapabilityError):
        reg.register(_spec("a"))


def test_for_surface_filters() -> None:
    """T-REG-2: for_surface returns only capabilities declaring that surface."""
    reg = Registry()
    reg.register(_spec("api_only", Surface.API))
    reg.register(_spec("mcp_only", Surface.MCP))
    reg.register(_spec("both", Surface.API | Surface.MCP))
    api_names = {c.name for c in reg.for_surface(Surface.API)}
    assert api_names == {"api_only", "both"}
    mcp_names = {c.name for c in reg.for_surface(Surface.MCP)}
    assert mcp_names == {"mcp_only", "both"}


def _make_module(name: str, *, with_register: bool) -> types.ModuleType:
    mod = types.ModuleType(name)
    if with_register:

        def register(registry: Registry) -> None:
            registry.register(_spec(f"{name}_cap"))

        mod.register = register  # type: ignore[attr-defined]
    sys.modules[name] = mod
    return mod


def test_discover_missing_register_raises() -> None:
    """T-DISC-1: a module without register(registry) raises MissingRegisterError."""
    _make_module("fake_pkg_no_reg", with_register=False)
    reg = Registry()
    with pytest.raises(MissingRegisterError):
        discover_and_register(reg, ["fake_pkg_no_reg"])
    del sys.modules["fake_pkg_no_reg"]


def test_discover_calls_each_register_once() -> None:
    """T-DISC-2: push registration calls each module's register exactly once."""
    _make_module("fake_pkg_a", with_register=True)
    _make_module("fake_pkg_b", with_register=True)
    reg = Registry()
    discover_and_register(reg, ["fake_pkg_a", "fake_pkg_b"])
    names = {c.name for c in reg.all()}
    assert names == {"fake_pkg_a_cap", "fake_pkg_b_cap"}
    del sys.modules["fake_pkg_a"]
    del sys.modules["fake_pkg_b"]
