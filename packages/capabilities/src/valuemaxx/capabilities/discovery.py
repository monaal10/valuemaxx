"""Push registration — each logic package exposes ``register(registry)`` (§3, H6).

``discover_and_register`` imports each named module and calls its ``register``.
A module missing ``register`` is a hard error, so ``valuemaxx.capabilities`` never
becomes a god-module that has to know about every logic package.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

from valuemaxx.capabilities.errors import MissingRegisterError

if TYPE_CHECKING:
    from collections.abc import Iterable

    from valuemaxx.capabilities.registry import Registry


def discover_and_register(registry: Registry, modules: Iterable[str]) -> None:
    """Import each module and call its ``register(registry)`` exactly once.

    Raises :class:`MissingRegisterError` if a module does not expose a callable
    ``register``.
    """
    for module_name in modules:
        module = importlib.import_module(module_name)
        register = getattr(module, "register", None)
        if not callable(register):
            raise MissingRegisterError(
                f"module {module_name!r} does not expose a callable register(registry)"
            )
        register(registry)


__all__ = ["discover_and_register"]
