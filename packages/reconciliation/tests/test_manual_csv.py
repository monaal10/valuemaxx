"""Manual CSV reconciliation — the Bedrock/Vertex/Azure upload path (§5.3).

Providers without a programmatic cost API (Bedrock, Vertex, Azure) are reconciled
by uploading their billing CSV; the parsed rows carry ``manual_reconciled``
provenance, never ``provider_reconciled``.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest
from valuemaxx.core import Provenance, TenantId
from valuemaxx.reconciliation.manual_csv import ManualCsvError, parse_manual_csv

TENANT = TenantId(UUID("00000000-0000-0000-0000-0000000000a1"))

_CSV = """provider,project,model,token_class,day,billed_usd
bedrock,acct-1,claude-3-5-sonnet,input_uncached,2026-06-27,12.50
vertex,acct-2,gemini-2,output,2026-06-27,3.0000000001
"""


def test_parses_rows_with_manual_reconciled_provenance() -> None:
    """Every parsed row is labeled manual_reconciled (never provider_reconciled)."""
    rows = parse_manual_csv(_CSV, tenant_id=TENANT)
    assert len(rows) == 2
    assert all(row.provenance is Provenance.MANUAL_RECONCILED for row in rows)


def test_billed_usd_is_decimal_not_float() -> None:
    """The billed amount is parsed as exact Decimal, preserving full precision."""
    rows = parse_manual_csv(_CSV, tenant_id=TENANT)
    assert rows[0].billed_usd == Decimal("12.50")
    assert rows[1].billed_usd == Decimal("3.0000000001")
    assert all(isinstance(row.billed_usd, Decimal) for row in rows)


def test_row_carries_tenant_and_match_key_parts() -> None:
    """Each row carries its tenant scope and the five match-key components."""
    rows = parse_manual_csv(_CSV, tenant_id=TENANT)
    first = rows[0]
    assert first.tenant_id == TENANT
    assert first.match_key == (
        "bedrock",
        "acct-1",
        "claude-3-5-sonnet",
        "input_uncached",
        "2026-06-27",
    )


def test_missing_required_column_raises_typed_error() -> None:
    """A CSV missing a required column raises a typed ManualCsvError, never KeyError."""
    bad = "provider,model,day,billed_usd\nbedrock,claude,2026-06-27,1.0\n"
    with pytest.raises(ManualCsvError, match="missing required column"):
        parse_manual_csv(bad, tenant_id=TENANT)


def test_non_decimal_amount_raises_typed_error() -> None:
    """A non-numeric billed_usd cell raises a typed error, not a bare ValueError."""
    header = "provider,project,model,token_class,day,billed_usd\n"
    bad = header + "bedrock,a,m,output,2026-06-27,not-a-number\n"
    with pytest.raises(ManualCsvError, match="not a valid decimal"):
        parse_manual_csv(bad, tenant_id=TENANT)


def test_empty_csv_returns_no_rows() -> None:
    """A header-only CSV parses to zero rows (not an error)."""
    rows = parse_manual_csv("provider,project,model,token_class,day,billed_usd\n", tenant_id=TENANT)
    assert rows == ()


def test_negative_amount_raises() -> None:
    """A negative billed amount is rejected (invoices are non-negative)."""
    header = "provider,project,model,token_class,day,billed_usd\n"
    bad = header + "bedrock,a,m,output,2026-06-27,-1.0\n"
    with pytest.raises(ManualCsvError, match="non-negative"):
        parse_manual_csv(bad, tenant_id=TENANT)


def test_row_provenance_cannot_be_overridden_to_non_manual() -> None:
    """A manual CSV row may not be constructed with a non-manual provenance (§5.3)."""
    from valuemaxx.reconciliation.schemas import ManualReconciliationRow

    with pytest.raises(ValueError, match="manual_reconciled"):
        ManualReconciliationRow(
            tenant_id=TENANT,
            provider="bedrock",
            project="a",
            model="m",
            token_class="output",
            day="2026-06-27",
            billed_usd=Decimal("1"),
            provenance=Provenance.PROVIDER_RECONCILED,
        )
