"""Capability registration hook — the store is an adapter, exposes no capability (M10).

Every logic package exposes ``register(registry)`` so ``discover_and_register`` can
call it uniformly (push registration, §3/H6). The store is the persistence *adapter*;
it serves no product capability of its own (those live in capture/outcomes/eval/etc.),
so this hook is intentionally a no-op. It exists only so the registry never has to
special-case the store.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from valuemaxx.capabilities import Registry


def register(registry: Registry) -> None:
    """Register the store's capabilities — none; the store is a persistence adapter."""
    # Intentionally empty: the store exposes no product capability (M10).
    _ = registry


__all__ = ["register"]
