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
from typing import TYPE_CHECKING, TypeVar

from typing_extensions import override
from valuemaxx.capabilities import (
    MissingRegisterError,
    Registry,
)

if TYPE_CHECKING:
    from pydantic import BaseModel
    from valuemaxx.capabilities import CapabilitySpec

_I = TypeVar("_I", bound="BaseModel")
_O = TypeVar("_O", bound="BaseModel")

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


class _DiscoveryRegistry(Registry):
    """A registry that tolerates ONLY the documented duplicate names during assembly.

    Discovery registers each module's ``register(registry)`` **directly** onto this
    one registry (never a per-module staging copy), so a capability handler that
    closes over a late-bound runtime holder keyed by the registry object binds to the
    very registry the surfaces project from — the app can then call
    ``bind_runtime(registry, ...)`` against it. A second registration of a
    :data:`KNOWN_DUPLICATE_NAMES` name is silently skipped (the first, per
    :data:`DEFAULT_CAPABILITY_MODULES` order, wins); every *other* duplicate is still
    a hard :class:`~valuemaxx.capabilities.DuplicateCapabilityError`.
    """

    @override
    def register(self, spec: CapabilitySpec[_I, _O]) -> None:
        """Register ``spec``, skipping a re-registration of an allowlisted duplicate name."""
        if spec.name in self._known_present() and spec.name in KNOWN_DUPLICATE_NAMES:
            return
        super().register(spec)

    def _known_present(self) -> frozenset[str]:
        return frozenset(cap.name for cap in self.all())


def register_modules(registry: Registry, modules: list[str]) -> None:
    """Register each module's capabilities into ``registry`` in order.

    Imports each module and calls its ``register(registry)`` **directly** on
    ``registry`` (no per-module staging copy), so a module's late-bound runtime
    holder — keyed by the registry object — binds to the registry the surfaces
    project from (the app wires it with ``bind_runtime(registry, runtime)``). When
    ``registry`` is a :class:`_DiscoveryRegistry`, a re-registration of a documented
    :data:`KNOWN_DUPLICATE_NAMES` name is skipped (the first wins); any other
    duplicate raises :class:`~valuemaxx.capabilities.DuplicateCapabilityError`,
    preserving the registry's no-silent-overwrite contract.
    """
    for module_name in modules:
        module = importlib.import_module(module_name)
        register = getattr(module, "register", None)
        if not callable(register):
            raise MissingRegisterError(
                f"module {module_name!r} does not expose a callable register(registry)"
            )
        register(registry)


def build_default_registry() -> Registry:
    """Build the canonical registry from every logic package's ``register``.

    Returns a fully-populated :class:`~valuemaxx.capabilities.Registry`. Assembly
    is deterministic and total: the one documented duplicate name is de-duplicated
    (see :data:`KNOWN_DUPLICATE_NAMES`); any unexpected duplicate raises.
    Also registers the agent-integrability scaffold/validate helper capabilities
    (``scaffold_outcome_rule`` / ``validate_init``) — the ``scaffold_*`` / ``validate_*``
    tools projected onto MCP among other surfaces.
    """
    from valuemaxx.agent_integrability.scaffold_caps import register_scaffold_caps

    registry = _DiscoveryRegistry()
    register_modules(registry, DEFAULT_CAPABILITY_MODULES)
    register_scaffold_caps(registry)
    return registry


__all__ = [
    "DEFAULT_CAPABILITY_MODULES",
    "KNOWN_DUPLICATE_NAMES",
    "build_default_registry",
    "register_modules",
]
