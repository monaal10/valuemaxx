"""Provider Cost API clients — OpenAI / Anthropic true-up, admin-key gated (§5.3).

The clients fetch authoritative daily billed totals from each provider's cost API
(OpenAI Costs 1d; Anthropic cost_report 1d + usage_report). They require an Admin
key (the cost APIs are admin-scoped) and must NEVER log the key — the secret is
held only long enough to build the Authorization header.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from valuemaxx.reconciliation.provider_api import (
    AdminKeyRequiredError,
    AnthropicCostClient,
    BilledTotal,
    OpenAICostClient,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

_SENTINEL = "sk-admin-SENTINEL-do-not-log-0xCAFE"


class _StubTransport:
    """A canned cost-API transport that records the headers it was handed."""

    def __init__(self, payload: object) -> None:
        self._payload = payload
        self.seen_headers: list[dict[str, str]] = []

    def get(self, url: str, headers: Mapping[str, str]) -> object:
        self.seen_headers.append(dict(headers))
        return self._payload


_OPENAI_PAYLOAD = {
    "data": [
        {
            "project_id": "proj-1",
            "model": "gpt-5",
            "line_item": "input_uncached",
            "amount": {"value": "12.5", "currency": "usd"},
        }
    ]
}

_ANTHROPIC_PAYLOAD = {
    "data": [
        {
            "workspace_id": "ws-1",
            "model": "claude-sonnet-4",
            "token_class": "output",
            "cost_usd": "3.25",
        }
    ]
}


def test_openai_client_returns_billed_totals() -> None:
    """The OpenAI client maps the Costs payload to BilledTotal rows (Decimal money)."""
    client = OpenAICostClient(transport=_StubTransport(_OPENAI_PAYLOAD), admin_key=_SENTINEL)
    totals = client.fetch_daily_costs(day="2026-06-27")
    assert totals == (
        BilledTotal(
            provider="openai",
            project="proj-1",
            model="gpt-5",
            token_class="input_uncached",
            day="2026-06-27",
            billed_usd=Decimal("12.5"),
        ),
    )


def test_anthropic_client_returns_billed_totals() -> None:
    """The Anthropic client maps cost_report rows to BilledTotal (Decimal money)."""
    client = AnthropicCostClient(transport=_StubTransport(_ANTHROPIC_PAYLOAD), admin_key=_SENTINEL)
    totals = client.fetch_daily_costs(day="2026-06-27")
    assert totals[0].provider == "anthropic"
    assert totals[0].billed_usd == Decimal("3.25")
    assert totals[0].project == "ws-1"


def test_admin_key_precondition_rejects_empty_key() -> None:
    """An empty / blank admin key is rejected up front (the cost API needs admin scope)."""
    with pytest.raises(AdminKeyRequiredError):
        OpenAICostClient(transport=_StubTransport(_OPENAI_PAYLOAD), admin_key="   ")


def test_key_is_sent_in_authorization_header_but_never_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The key reaches the Authorization header yet appears in no log record."""
    transport = _StubTransport(_OPENAI_PAYLOAD)
    client = OpenAICostClient(transport=transport, admin_key=_SENTINEL)
    with caplog.at_level(logging.DEBUG):
        client.fetch_daily_costs(day="2026-06-27")
    # the key was actually used to authenticate...
    assert any(_SENTINEL in h.get("Authorization", "") for h in transport.seen_headers)
    # ...but it never leaked into a log record.
    assert all(_SENTINEL not in rec.getMessage() for rec in caplog.records)


def test_repr_does_not_leak_key() -> None:
    """repr() of a client never exposes the admin key (it is not a public attribute)."""
    client = OpenAICostClient(transport=_StubTransport(_OPENAI_PAYLOAD), admin_key=_SENTINEL)
    assert _SENTINEL not in repr(client)
    anthropic = AnthropicCostClient(
        transport=_StubTransport(_ANTHROPIC_PAYLOAD), admin_key=_SENTINEL
    )
    assert _SENTINEL not in repr(anthropic)


def test_anthropic_admin_key_precondition() -> None:
    """The Anthropic client also requires a non-blank admin key."""
    with pytest.raises(AdminKeyRequiredError):
        AnthropicCostClient(transport=_StubTransport(_ANTHROPIC_PAYLOAD), admin_key="")


def test_payload_missing_data_array_raises() -> None:
    """A cost-API payload without a 'data' array raises a typed error."""
    from valuemaxx.reconciliation.provider_api import ProviderCostApiError

    client = OpenAICostClient(transport=_StubTransport({"oops": 1}), admin_key=_SENTINEL)
    with pytest.raises(ProviderCostApiError, match="missing 'data'"):
        client.fetch_daily_costs(day="2026-06-27")


def test_payload_data_not_a_list_raises() -> None:
    """A 'data' field that is not a list raises a typed error."""
    from valuemaxx.reconciliation.provider_api import ProviderCostApiError

    client = OpenAICostClient(transport=_StubTransport({"data": 5}), admin_key=_SENTINEL)
    with pytest.raises(ProviderCostApiError, match="not a list"):
        client.fetch_daily_costs(day="2026-06-27")


def test_non_dict_rows_are_skipped() -> None:
    """Non-dict rows in the 'data' array are skipped rather than crashing."""
    payload = {"data": ["not-a-row", _OPENAI_PAYLOAD["data"][0]]}
    client = OpenAICostClient(transport=_StubTransport(payload), admin_key=_SENTINEL)
    totals = client.fetch_daily_costs(day="2026-06-27")
    assert len(totals) == 1


def test_non_decimal_amount_raises() -> None:
    """An unparseable amount raises a typed ProviderCostApiError."""
    from valuemaxx.reconciliation.provider_api import ProviderCostApiError

    payload = {"data": [{"amount": {"value": "twelve"}}]}
    client = OpenAICostClient(transport=_StubTransport(payload), admin_key=_SENTINEL)
    with pytest.raises(ProviderCostApiError, match="non-decimal"):
        client.fetch_daily_costs(day="2026-06-27")
