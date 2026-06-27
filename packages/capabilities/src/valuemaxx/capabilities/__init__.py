"""valuemaxx.capabilities — the capability registry contract.

The single source of truth for every operation the product exposes. Surfaces
(API/MCP/CLI/NOTIFY) are thin projections of the registry built here. This
package imports only stdlib, pydantic, and typing — never a logic package, not
even ``valuemaxx.core`` domain models (capabilities carry their own pydantic I/O
models). The import discipline is asserted by a conformance rule.
"""

from __future__ import annotations

from valuemaxx.capabilities.decorator import CapabilitySpec, capability
from valuemaxx.capabilities.discovery import discover_and_register
from valuemaxx.capabilities.errors import (
    CapabilityDeclarationError,
    CapabilityError,
    DuplicateCapabilityError,
    MissingRegisterError,
)
from valuemaxx.capabilities.registry import AnyCapability, Registry
from valuemaxx.capabilities.surfaces import Mode, Surface

__all__ = [
    "AnyCapability",
    "CapabilityDeclarationError",
    "CapabilityError",
    "CapabilitySpec",
    "DuplicateCapabilityError",
    "MissingRegisterError",
    "Mode",
    "Registry",
    "Surface",
    "capability",
    "discover_and_register",
]
