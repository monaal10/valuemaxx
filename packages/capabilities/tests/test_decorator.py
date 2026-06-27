"""F0-CAPS: @capability declaration rules + CapabilitySpec shape."""

from __future__ import annotations

import pytest
from pydantic import BaseModel
from valuemaxx.capabilities.decorator import CapabilitySpec, capability
from valuemaxx.capabilities.errors import CapabilityDeclarationError
from valuemaxx.capabilities.surfaces import Mode, Surface


class _In(BaseModel):
    x: int


class _Out(BaseModel):
    y: int


def _handler(payload: _In) -> _Out:
    return _Out(y=payload.x + 1)


def test_capability_builds_a_spec() -> None:
    spec = capability(
        name="increment",
        input_model=_In,
        output_model=_Out,
        handler=_handler,
        description="add one",
        surfaces=Surface.API | Surface.MCP,
        mode=Mode.REQUEST_RESPONSE,
    )
    assert isinstance(spec, CapabilitySpec)
    assert spec.name == "increment"
    assert spec.input_model is _In
    assert spec.output_model is _Out
    assert Surface.API in spec.surfaces


def test_empty_description_rejected() -> None:
    """T-CAP-4: an empty description is rejected."""
    with pytest.raises(CapabilityDeclarationError):
        capability(
            name="x",
            input_model=_In,
            output_model=_Out,
            handler=_handler,
            description="   ",
            surfaces=Surface.API,
            mode=Mode.REQUEST_RESPONSE,
        )


def test_empty_surfaces_rejected() -> None:
    """T-CAP-3: an empty surface mask (Surface(0)) is rejected."""
    with pytest.raises(CapabilityDeclarationError):
        capability(
            name="x",
            input_model=_In,
            output_model=_Out,
            handler=_handler,
            description="ok",
            surfaces=Surface(0),
            mode=Mode.REQUEST_RESPONSE,
        )


def test_webhook_cannot_declare_cli() -> None:
    """T-CAP-5: a webhook_inbound capability cannot be projected to the CLI."""
    with pytest.raises(CapabilityDeclarationError):
        capability(
            name="x",
            input_model=_In,
            output_model=_Out,
            handler=_handler,
            description="ok",
            surfaces=Surface.CLI | Surface.API,
            mode=Mode.WEBHOOK_INBOUND,
        )


def test_spec_is_frozen() -> None:
    spec = capability(
        name="increment",
        input_model=_In,
        output_model=_Out,
        handler=_handler,
        description="add one",
        surfaces=Surface.API,
        mode=Mode.REQUEST_RESPONSE,
    )
    with pytest.raises((AttributeError, TypeError)):
        spec.name = "other"  # type: ignore[misc]  # frozen dataclass
