"""The @capability declaration and its frozen spec (the single source of truth).

A capability is declared once with typed pydantic input/output models, a handler,
a description, the surfaces it supports, and its mode. Surfaces are projected from
the registry; a capability is never hand-written into one surface only (§3, H5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Generic, TypeVar

from pydantic import BaseModel
from valuemaxx.capabilities.errors import CapabilityDeclarationError
from valuemaxx.capabilities.surfaces import Mode, Surface

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

InputT = TypeVar("InputT", bound=BaseModel)
OutputT = TypeVar("OutputT", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class CapabilitySpec(Generic[InputT, OutputT]):
    """One declared capability — typed I/O, handler, surfaces, and mode."""

    name: str
    input_model: type[InputT]
    output_model: type[OutputT]
    handler: Callable[[InputT], OutputT]
    description: str
    surfaces: Surface
    mode: Mode
    examples: tuple[object, ...] = field(default_factory=tuple)


def capability(
    *,
    name: str,
    input_model: type[InputT],
    output_model: type[OutputT],
    handler: Callable[[InputT], OutputT],
    description: str,
    surfaces: Surface,
    mode: Mode,
    examples: Sequence[object] = (),
) -> CapabilitySpec[InputT, OutputT]:
    """Declare a capability, validating its declaration rules.

    Rejects an empty description, an empty surface mask (``Surface(0)``), and a
    ``webhook_inbound`` capability that declares the CLI surface (an inbound
    webhook is not a CLI command).
    """
    if not description.strip():
        raise CapabilityDeclarationError(f"capability {name!r} has an empty description")
    if not surfaces:
        raise CapabilityDeclarationError(f"capability {name!r} declares no surfaces")
    if mode is Mode.WEBHOOK_INBOUND and Surface.CLI in surfaces:
        raise CapabilityDeclarationError(
            f"capability {name!r} is webhook_inbound and cannot declare the CLI surface"
        )
    return CapabilitySpec(
        name=name,
        input_model=input_model,
        output_model=output_model,
        handler=handler,
        description=description,
        surfaces=surfaces,
        mode=mode,
        examples=tuple(examples),
    )


__all__ = ["CapabilitySpec", "capability"]
