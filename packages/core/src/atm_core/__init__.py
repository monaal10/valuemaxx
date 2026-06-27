"""atm_core — the typed spine for AI Margin Intelligence.

This package is the single source of truth for every domain type: enums, ids,
the strict pydantic bases, domain event models, rollup helpers, and the
repository ABCs every other package depends on. No other package may redefine a
domain type (enforced by the ``no_type_outside_core`` conformance rule).

The full public surface (with an explicit ``__all__``) is assembled in
F0-CORE-INIT once the submodules exist.
"""

__all__: list[str] = []
