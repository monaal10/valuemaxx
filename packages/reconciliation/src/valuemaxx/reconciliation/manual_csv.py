"""Manual CSV reconciliation — the Bedrock/Vertex/Azure upload path (§5.3).

Bedrock, Vertex, and Azure have no programmatic per-request cost API, so their
authoritative spend is reconciled by uploading the provider's billing CSV. Each
parsed row is labeled ``manual_reconciled`` (distinct from the ``provider_
reconciled`` programmatic path) and carries the (provider, project, model,
token_class, day) match key plus the billed amount as exact :class:`~decimal.
Decimal`.

Missing columns and unparseable amounts raise a typed :class:`ManualCsvError`,
never a bare ``KeyError``/``ValueError`` — the failure is explicit and catchable.
"""

from __future__ import annotations

import csv
import io
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

from valuemaxx.core import AtmError
from valuemaxx.reconciliation.schemas import ManualReconciliationRow

if TYPE_CHECKING:
    from valuemaxx.core import TenantId

_REQUIRED_COLUMNS: tuple[str, ...] = (
    "provider",
    "project",
    "model",
    "token_class",
    "day",
    "billed_usd",
)


class ManualCsvError(AtmError):
    """An uploaded reconciliation CSV was malformed (missing column / bad amount)."""


def _parse_amount(raw: str, *, line: int) -> Decimal:
    """Parse a billed_usd cell into exact Decimal, raising a typed error on failure."""
    try:
        return Decimal(raw.strip())
    except InvalidOperation as exc:
        raise ManualCsvError(f"row {line}: billed_usd {raw!r} is not a valid decimal") from exc


def parse_manual_csv(text: str, *, tenant_id: TenantId) -> tuple[ManualReconciliationRow, ...]:
    """Parse an uploaded provider billing CSV into manual-reconciled rows.

    Args:
        text: the raw CSV text, with a header row naming the required columns.
        tenant_id: the tenant the upload belongs to (stamped on every row).

    Returns:
        One :class:`~valuemaxx.reconciliation.schemas.ManualReconciliationRow` per
        data row, each labeled ``manual_reconciled``.

    Raises:
        ManualCsvError: if a required column is missing, an amount is unparseable,
            or an amount is negative.
    """
    reader = csv.DictReader(io.StringIO(text))
    header = reader.fieldnames or []
    missing = [col for col in _REQUIRED_COLUMNS if col not in header]
    if missing:
        raise ManualCsvError(f"missing required column(s): {', '.join(missing)}")

    rows: list[ManualReconciliationRow] = []
    for line, record in enumerate(reader, start=2):
        billed = _parse_amount(record["billed_usd"], line=line)
        try:
            rows.append(
                ManualReconciliationRow(
                    tenant_id=tenant_id,
                    provider=record["provider"],
                    project=record["project"],
                    model=record["model"],
                    token_class=record["token_class"],
                    day=record["day"],
                    billed_usd=billed,
                )
            )
        except ValueError as exc:
            # the model_validator rejects negative amounts; surface it as a typed error.
            raise ManualCsvError(f"row {line}: {exc}") from exc
    return tuple(rows)


__all__ = ["ManualCsvError", "parse_manual_csv"]
