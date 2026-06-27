"""The canonical capability-discovery module — the registry every surface projects.

Each logic package exposes a module-level ``register(registry)`` (push
registration, §3/H6). This module names them once and assembles the full
capability set into a single :class:`~valuemaxx.capabilities.Registry`. The
surface apps (API/MCP/CLI/NOTIFY) import :func:`build_default_registry` and
project from it — they never hand-pick which capabilities exist.

One pre-existing overlap is tolerated: both ``valuemaxx.outcomes.capabilities``
and ``valuemaxx.onboarding.service`` declare a ``validate_outcome_rule``
capability (semantically the same safe-predicate validation). The outcomes
package owns the canonical declaration; the onboarding duplicate is skipped via
:data:`KNOWN_DUPLICATE_NAMES`. Every *other* duplicate name remains a hard error
— the registry's no-silent-overwrite contract is preserved for anything not on
this short, documented allowlist.
"""

from __future__ import annotations

import importlib

from valuemaxx.capabilities import (
    DuplicateCapabilityError,
    MissingRegisterError,
    Registry,
)

# The nine logic packages, in deterministic registration order. ``outcomes``
# precedes ``onboarding`` so the outcomes-owned ``validate_outcome_rule`` wins.
DEFAULT_CAPABILITY_MODULES: list[str] = [
    "valuemaxx.capture.capabilities",
    "valuemaxx.outcomes.capabilities",
    "valuemaxx.attribution.capabilities",
    "valuemaxx.reconciliation.capabilities",
    "valuemaxx.allocation.capabilities",
    "valuemaxx.metrics.capabilities",
    "valuemaxx.eval.capabilities",
    "valuemaxx.onboarding.service",
    "valuemaxx.store.capabilities",
]

# Capability names declared by more than one package on purpose. The first
# registration (per DEFAULT_CAPABILITY_MODULES order) is kept; later duplicates of
# these names are skipped instead of raising. Any duplicate NOT listed here is a
# hard error (DuplicateCapabilityError), preserving the registry contract.
KNOWN_DUPLICATE_NAMES: frozenset[str] = frozenset({"validate_outcome_rule"})


def register_modules(registry: Registry, modules: list[str]) -> None:
    """Register each module's capabilities into ``registry`` in order.

    Imports each module and calls its ``register`` against a per-module staging
    registry, then copies the specs across — skipping only a duplicate name on the
    documented :data:`KNOWN_DUPLICATE_NAMES` allowlist. An un-allowlisted duplicate
    raises :class:`~valuemaxx.capabilities.DuplicateCapabilityError`, preserving the
    registry's no-silent-overwrite contract. Because each module registers into its
    own staging registry first, a tolerated collision never leaves ``registry`` in
    a half-populated state.
    """
    seen: set[str] = set()
    for module_name in modules:
        module = importlib.import_module(module_name)
        register = getattr(module, "register", None)
        if not callable(register):
            raise MissingRegisterError(
                f"module {module_name!r} does not expose a callable register(registry)"
            )
        staging = Registry()
        register(staging)
        for cap in staging.all():
            if cap.name in seen:
                if cap.name in KNOWN_DUPLICATE_NAMES:
                    continue
                raise DuplicateCapabilityError(
                    f"capability {cap.name!r} is already registered"
                )
            registry.register(cap)
            seen.add(cap.name)


def build_default_registry() -> Registry:
    """Build the canonical registry from every logic package's ``register``.

    Returns a fully-populated :class:`~valuemaxx.capabilities.Registry`. Assembly
    is deterministic and total: the one documented duplicate name is de-duplicated
    (see :data:`KNOWN_DUPLICATE_NAMES`); any unexpected duplicate raises.
    """
    registry = Registry()
    register_modules(registry, DEFAULT_CAPABILITY_MODULES)
    return registry


__all__ = [
    "DEFAULT_CAPABILITY_MODULES",
    "KNOWN_DUPLICATE_NAMES",
    "build_default_registry",
    "register_modules",
]
