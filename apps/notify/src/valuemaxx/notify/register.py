"""Capability registration hook — notify is a sink, exposes no capability.

Every discoverable module exposes ``register(registry)`` (push registration,
§3/H6). The notify surface is a digest *sink*: it consumes the existing rollup
capabilities (metrics/allocation/eval) and produces no product capability of its
own, so this hook is intentionally a no-op (mirrors the store adapter).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from valuemaxx.capabilities import Registry


def register(registry: Registry) -> None:
    """Register the notify surface's capabilities — none; it is a digest sink."""
    # Intentionally empty: notify reads rollups via existing capabilities and emits
    # digests; it declares no capability of its own (M10).
    _ = registry


__all__ = ["register"]
