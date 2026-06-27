"""Typed domain errors — one ``AtmError`` root, never a bare ``Exception``.

AGENTS.md §5 forbids bare ``except:`` and swallowing. Downstream code catches
:class:`AtmError` (or a specific subclass), never the base ``Exception``.
"""

from __future__ import annotations


class AtmError(Exception):
    """Base class for every error raised by the AI Margin Intelligence domain."""


class TenantScopeError(AtmError):
    """A tenant-scoping invariant was violated (missing/None tenant_id, §3.2)."""


class ProvenanceWarning(AtmError):  # noqa: N818 — design-mandated public name (plan §F0-CORE-1a); it is a raised AtmError, not a warnings.Warning
    """A cost-capture invariant was violated and logged, never silently dropped (§5.2)."""


class HonestyInvariantError(AtmError):
    """An attempt to construct an honesty-axis-violating state (§3.1, §4).

    Raised when code tries to render an estimate as billed, an inferred match as
    exact, or an attempt as a confirmed outcome.
    """


class CaptureError(AtmError):
    """A cost-capture path failed (the SDK fails open and never propagates this, §5.1)."""


class BindingAmbiguityError(AtmError):
    """An outcome->run binding could not be resolved unambiguously (§6.3)."""


__all__ = [
    "AtmError",
    "BindingAmbiguityError",
    "CaptureError",
    "HonestyInvariantError",
    "ProvenanceWarning",
    "TenantScopeError",
]
