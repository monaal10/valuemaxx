"""F0-CORE-1a: ProvenanceLabel link rules (both directions).

Reconciled provenance REQUIRES a reconciliation_record_id; non-reconciled
provenance must NOT carry one. This keeps "reconciled" honest — it can only be
claimed when it points at the additive record that justifies it.
"""

from __future__ import annotations

import pytest
from atm_core.enums import Provenance
from atm_core.provenance import ProvenanceLabel
from pydantic import ValidationError


def test_reconciled_requires_record_id() -> None:
    """T-PL-1: PROVIDER_RECONCILED / MANUAL_RECONCILED require a record id."""
    for prov in (Provenance.PROVIDER_RECONCILED, Provenance.MANUAL_RECONCILED):
        with pytest.raises(ValidationError):
            ProvenanceLabel(provenance=prov)


def test_reconciled_with_record_id_ok() -> None:
    label = ProvenanceLabel(
        provenance=Provenance.PROVIDER_RECONCILED,
        reconciliation_record_id="rec-1",
    )
    assert label.reconciliation_record_id == "rec-1"


def test_unreconciled_forbids_record_id() -> None:
    """T-PL-2: a non-reconciled provenance must not carry a reconciliation id."""
    for prov in (Provenance.MEASURED, Provenance.ESTIMATED, Provenance.ALLOCATED):
        with pytest.raises(ValidationError):
            ProvenanceLabel(provenance=prov, reconciliation_record_id="rec-1")


def test_unreconciled_without_record_id_ok() -> None:
    label = ProvenanceLabel(provenance=Provenance.MEASURED)
    assert label.reconciliation_record_id is None
    assert label.provenance is Provenance.MEASURED


def test_note_is_optional() -> None:
    label = ProvenanceLabel(provenance=Provenance.ESTIMATED, note="token-derived")
    assert label.note == "token-derived"
