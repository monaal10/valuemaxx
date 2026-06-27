"""The strict pydantic bases every domain model inherits.

:class:`StrictModel` is ``frozen`` (immutable), ``extra="forbid"`` (no stray
fields), and ``strict`` (no silent coercion — ``"5"`` is not int ``5``). Validate
at the boundary, trust the types inside.

:class:`TenantScopedModel` adds the required, non-nullable ``tenant_id`` (§3.2):
an untenanted event cannot be constructed. It also rejects naive datetimes on any
field — time must be explicitly tz-aware (UTC), never ambiguous.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator
from valuemaxx.core.ids import TenantId


class StrictModel(BaseModel):
    """Immutable, extra-forbidding, strict pydantic base for all domain models."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class TenantScopedModel(StrictModel):
    """A :class:`StrictModel` that is structurally bound to one tenant (§3.2).

    ``tenant_id`` has no default, so constructing an event without a tenant — or
    with ``None`` — raises at the pydantic boundary. Isolation is structural, not
    disciplinary.
    """

    tenant_id: TenantId

    @field_validator("*", mode="before")
    @classmethod
    def _reject_naive_datetimes(cls, value: object) -> object:
        """Reject naive datetimes on any field; require tz-aware (UTC) time.

        Typed ``object`` (not ``Any``): a ``mode="before"`` validator over all
        fields sees raw, unvalidated input, and we only narrow it via isinstance.
        """
        if isinstance(value, datetime) and value.tzinfo is None:
            raise ValueError("naive datetime forbidden; supply tz-aware UTC")
        return value


__all__ = ["StrictModel", "TenantScopedModel"]
