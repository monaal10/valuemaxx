"""The provenance label carried by every cost-bearing field (§3.1).

A :class:`ProvenanceLabel` pairs a :class:`~atm_core.enums.Provenance` value with
an optional link to the additive reconciliation record that justifies it. The
link rules keep "reconciled" honest in both directions: a reconciled provenance
*requires* a record id, and a non-reconciled provenance must *not* carry one
(you cannot label something reconciled without pointing at the record).
"""

from __future__ import annotations

from pydantic import model_validator

from atm_core.base import StrictModel
from atm_core.enums import Provenance

_RECONCILED = frozenset({Provenance.PROVIDER_RECONCILED, Provenance.MANUAL_RECONCILED})


class ProvenanceLabel(StrictModel):
    """Cost provenance plus the optional link to its reconciliation record."""

    provenance: Provenance
    reconciliation_record_id: str | None = None
    note: str | None = None

    @model_validator(mode="after")
    def _check_reconciliation_link(self) -> ProvenanceLabel:
        """Enforce the reconciled<->record-id link in both directions."""
        is_reconciled = self.provenance in _RECONCILED
        has_record = self.reconciliation_record_id is not None
        if is_reconciled and not has_record:
            raise ValueError(
                f"provenance {self.provenance.value!r} requires a reconciliation_record_id"
            )
        if not is_reconciled and has_record:
            raise ValueError(
                f"provenance {self.provenance.value!r} must not carry a "
                "reconciliation_record_id (only reconciled provenance may)"
            )
        return self


__all__ = ["ProvenanceLabel"]
