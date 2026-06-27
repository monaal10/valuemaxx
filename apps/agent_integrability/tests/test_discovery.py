"""Tests for the canonical capability-discovery module (the shared registry).

The discovery module is the single place that names every logic package's
``register(registry)`` entry point and assembles them into one
:class:`~valuemaxx.capabilities.Registry`. Every surface app (API/MCP/CLI/NOTIFY)
projects from a registry built here, so the projection layer never hand-picks
capabilities.
"""

from __future__ import annotations

from valuemaxx.agent_integrability.discovery import (
    DEFAULT_CAPABILITY_MODULES,
    KNOWN_DUPLICATE_NAMES,
    build_default_registry,
)
from valuemaxx.capabilities import DuplicateCapabilityError, Registry, Surface


def test_default_modules_cover_every_logic_package() -> None:
    """The canonical module list names each of the nine logic packages once."""
    expected = {
        "valuemaxx.capture.capabilities",
        "valuemaxx.outcomes.capabilities",
        "valuemaxx.attribution.capabilities",
        "valuemaxx.reconciliation.capabilities",
        "valuemaxx.allocation.capabilities",
        "valuemaxx.metrics.capabilities",
        "valuemaxx.eval.capabilities",
        "valuemaxx.onboarding.service",
        "valuemaxx.store.capabilities",
    }
    assert set(DEFAULT_CAPABILITY_MODULES) == expected
    # registration order is deterministic (a list, not a set)
    assert len(DEFAULT_CAPABILITY_MODULES) == len(set(DEFAULT_CAPABILITY_MODULES))


def test_build_default_registry_returns_registry() -> None:
    """build_default_registry assembles a populated Registry."""
    registry = build_default_registry()
    assert isinstance(registry, Registry)
    assert registry.all(), "the default registry must contain capabilities"


def test_build_default_registry_is_collision_free() -> None:
    """Building the canonical registry never raises despite the known overlap.

    ``validate_outcome_rule`` is declared by BOTH outcomes and onboarding; the
    canonical builder keeps the first (outcomes) and skips the allowlisted
    duplicate, so assembling the full set is deterministic and total.
    """
    registry = build_default_registry()
    names = [cap.name for cap in registry.all()]
    assert names.count("validate_outcome_rule") == 1


def test_outcomes_owns_validate_outcome_rule() -> None:
    """The surviving validate_outcome_rule is the outcomes-package one."""
    registry = build_default_registry()
    cap = next(c for c in registry.all() if c.name == "validate_outcome_rule")
    assert cap.input_model.__module__.startswith("valuemaxx.outcomes")


def test_known_duplicate_names_documents_the_overlap() -> None:
    """The only tolerated duplicate is the documented validate_outcome_rule overlap."""
    assert set(KNOWN_DUPLICATE_NAMES) == {"validate_outcome_rule"}


def test_unexpected_duplicate_still_raises() -> None:
    """A duplicate that is NOT allowlisted is still a hard error (contract intact)."""
    registry = Registry()
    from valuemaxx.agent_integrability.discovery import register_modules

    # Registering capture twice produces an un-allowlisted duplicate.
    try:
        register_modules(
            registry,
            ["valuemaxx.capture.capabilities", "valuemaxx.capture.capabilities"],
        )
    except DuplicateCapabilityError:
        pass
    else:  # pragma: no cover - defensive
        raise AssertionError("expected DuplicateCapabilityError for un-allowlisted duplicate")


def test_every_capability_declares_at_least_one_surface() -> None:
    """Every discovered capability is projectable onto at least one surface."""
    registry = build_default_registry()
    for cap in registry.all():
        assert cap.surfaces, f"{cap.name} declares no surfaces"


def test_registry_partitions_by_surface() -> None:
    """for_surface returns exactly the capabilities declaring that surface."""
    registry = build_default_registry()
    for surface in (Surface.API, Surface.MCP, Surface.CLI, Surface.NOTIFY):
        projected = registry.for_surface(surface)
        assert all(surface in cap.surfaces for cap in projected)
        projected_names = {cap.name for cap in projected}
        expected_names = {c.name for c in registry.all() if surface in c.surfaces}
        assert projected_names == expected_names
