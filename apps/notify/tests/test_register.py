"""Notify register-hook test — notify is a sink, exposes no product capability.

For uniformity every module that can be discovered exposes ``register(registry)``;
the notify surface is a digest *sink*, not a capability producer (its inputs are
the existing rollup capabilities), so its hook is intentionally a no-op.
"""

from __future__ import annotations

from valuemaxx.capabilities import Registry
from valuemaxx.notify import register


def test_register_is_a_noop_sink_hook() -> None:
    """register adds no capability (notify consumes capabilities; it produces none)."""
    registry = Registry()
    register(registry)
    assert registry.all() == ()
