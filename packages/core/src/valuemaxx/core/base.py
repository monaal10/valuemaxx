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

    @field_validator("*", mode="after")
    @classmethod
    def _reject_naive_datetimes(cls, value: object) -> object:
        """Reject naive datetimes on any field; require tz-aware (UTC) time.

        ``mode="after"`` is LOAD-BEARING, not a style choice. A wildcard
        ``mode="before"`` validator makes pydantic hand every field its *Python*
        value instead of the raw JSON token, which silently disables JSON-mode
        parsing for the whole model: under ``strict=True`` a JSON datetime string
        then fails with ``datetime_type`` and a JSON array fails ``frozen_set_type``,
        even via ``model_validate_json``. That made EVERY tenant-scoped capability
        with a datetime or set field uncallable over HTTP — ``bind_outcome`` and
        ``ingest_webhook_outcome`` among them — because the API projection validates
        wire payloads with ``model_validate_json``.

        Running after parsing keeps the invariant identical (a naive datetime is
        still rejected, whether it arrived as a Python ``datetime`` or a JSON string
        without an offset) while leaving JSON parsing intact. Typed ``object`` rather
        than ``Any``: the validator spans all fields, so we only narrow by isinstance.
        """
        if isinstance(value, datetime) and value.tzinfo is None:
            raise ValueError("naive datetime forbidden; supply tz-aware UTC")
        return value


__all__ = ["StrictModel", "TenantScopedModel"]
