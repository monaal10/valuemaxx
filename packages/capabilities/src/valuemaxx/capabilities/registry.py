"""The capability Registry — the single source every surface projects from."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar, cast

from pydantic import BaseModel
from valuemaxx.capabilities.decorator import CapabilitySpec
from valuemaxx.capabilities.errors import DuplicateCapabilityError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from valuemaxx.capabilities.surfaces import Surface

_I = TypeVar("_I", bound=BaseModel)
_O = TypeVar("_O", bound=BaseModel)

# Capabilities are stored erased to the most-general pydantic I/O bound. Concrete
# specs are ``CapabilitySpec[ConcreteIn, ConcreteOut]``; because the spec is
# invariant in its type params (``I`` appears in both ``type[I]`` and
# ``Callable[[I], O]``), a concrete spec is not statically assignable to this
# alias, so ``register`` accepts the concrete spec generically and erases it on
# storage. The erasure is sound: the registry only reads ``name``/``surfaces`` and
# hands the spec back to a surface that re-narrows via the carried model types.
AnyCapability = CapabilitySpec[BaseModel, BaseModel]


class Registry:
    """An ordered, name-unique collection of capability specs."""

    def __init__(self) -> None:
        self._by_name: dict[str, AnyCapability] = {}

    def register(self, spec: CapabilitySpec[_I, _O]) -> None:
        """Register a capability. A duplicate name is a hard error (no silent overwrite)."""
        if spec.name in self._by_name:
            raise DuplicateCapabilityError(f"capability {spec.name!r} is already registered")
        self._by_name[spec.name] = cast("AnyCapability", spec)

    def all(self) -> Sequence[AnyCapability]:
        """All registered capabilities, in registration order."""
        return tuple(self._by_name.values())

    def for_surface(self, surface: Surface) -> Sequence[AnyCapability]:
        """The capabilities that declare the given surface."""
        return tuple(spec for spec in self._by_name.values() if surface in spec.surfaces)


__all__ = ["AnyCapability", "Registry"]
