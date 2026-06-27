"""Typed errors for the capability registry."""

from __future__ import annotations


class CapabilityError(Exception):
    """Base class for every capability-registry error."""


class CapabilityDeclarationError(CapabilityError):
    """A @capability declaration is invalid (empty description/surfaces, bad mode mix)."""


class DuplicateCapabilityError(CapabilityError):
    """Two capabilities were registered under the same name (a hard error)."""


class MissingRegisterError(CapabilityError):
    """A discovered module does not expose ``register(registry)`` (push registration)."""


__all__ = [
    "CapabilityDeclarationError",
    "CapabilityError",
    "DuplicateCapabilityError",
    "MissingRegisterError",
]
