"""Parse-envelope schemas for reconciliation inputs (boundary validation).

These are NOT domain types — they are the validated wire/file envelopes the
reconciliation package parses external billing data into (the manual CSV upload
path for Bedrock/Vertex/Azure, §5.3). The authoritative domain type they feed —
:class:`~valuemaxx.core.ReconciliationRecord` — still lives only in
``valuemaxx.core``. This file is on the ``no_type_outside_core`` config-AST
allowlist (G1-EXIT item 7) precisely because it carries parse envelopes, not
domain models.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import model_validator
from valuemaxx.core import Provenance
from valuemaxx.core.base import TenantScopedModel


class ManualReconciliationRow(TenantScopedModel):
    """One row of an uploaded provider billing CSV, labeled ``manual_reconciled``.

    Carries the five match-key components and the authoritative billed amount for
    a (provider, project, model, token_class, day) unit. The provenance is fixed
    to :attr:`~valuemaxx.core.Provenance.MANUAL_RECONCILED` — the CSV-upload path
    is never ``provider_reconciled`` (which is reserved for programmatic cost APIs).
    """

    provider: str
    project: str
    model: str
    token_class: str
    day: str
    billed_usd: Decimal
    provenance: Provenance = Provenance.MANUAL_RECONCILED

    @property
    def match_key(self) -> tuple[str, str, str, str, str]:
        """The (provider, project, model, token_class, day) match key for this row."""
        return (self.provider, self.project, self.model, self.token_class, self.day)

    @model_validator(mode="after")
    def _check(self) -> ManualReconciliationRow:
        """Enforce manual_reconciled provenance and a non-negative billed amount."""
        if self.provenance is not Provenance.MANUAL_RECONCILED:
            raise ValueError("a manual CSV row must carry manual_reconciled provenance (§5.3)")
        if self.billed_usd < 0:
            raise ValueError("billed_usd must be non-negative")
        return self


__all__ = ["ManualReconciliationRow"]
