"""atm_capabilities — the capability registry contract.

The single source of truth for every operation the product exposes. Surfaces
(API/MCP/CLI/NOTIFY) are thin projections of the registry built here. This
package imports only stdlib, pydantic, and typing — never a logic package, not
even ``atm_core`` domain models (capabilities carry their own pydantic I/O
models). The import discipline is asserted by a conformance rule.
"""

__all__: list[str] = []
