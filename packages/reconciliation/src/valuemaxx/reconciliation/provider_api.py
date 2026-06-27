"""Provider Cost API clients — the programmatic true-up sources (§5.3).

These clients fetch the *authoritative* daily billed totals reconciliation prorates
against:

- :class:`OpenAICostClient` — the OpenAI Costs endpoint (1-day granularity).
- :class:`AnthropicCostClient` — the Anthropic ``cost_report`` (1-day) plus
  ``usage_report``.

Both cost APIs are **admin-scoped**: an Admin key is a precondition (the per-user
key cannot read org spend). The key is injected, held only long enough to build the
``Authorization`` header, and **never logged** — it is a private attribute, never
part of ``repr``, and never passed to a logger (the ``no_secret_logging`` rule, RECON
side). The HTTP transport is a :class:`CostApiTransport` Protocol so the clients are
unit-tested without network.

Bedrock / Vertex / Azure have no such API; they reconcile via the manual CSV upload
path (:mod:`valuemaxx.reconciliation.manual_csv`).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Protocol, cast, runtime_checkable

from typing_extensions import override
from valuemaxx.core import AtmError

if TYPE_CHECKING:
    from collections.abc import Mapping

_log = logging.getLogger("valuemaxx.reconciliation.provider_api")


class AdminKeyRequiredError(AtmError):
    """A provider cost API was used without the required Admin key (§5.3)."""


class ProviderCostApiError(AtmError):
    """A provider cost API returned a payload reconciliation could not parse."""


@dataclass(frozen=True, slots=True)
class BilledTotal:
    """One authoritative billed total for a match-key unit (NOT a domain model).

    A plain frozen dataclass — the authoritative domain artifact is the additive
    :class:`~valuemaxx.core.ReconciliationRecord`; this is just the cost-API row the
    service sums and prorates against.
    """

    provider: str
    project: str
    model: str
    token_class: str
    day: str
    billed_usd: Decimal


@runtime_checkable
class CostApiTransport(Protocol):
    """The injected HTTP boundary a cost client calls (so clients are network-free in tests)."""

    def get(self, url: str, headers: Mapping[str, str]) -> object:
        """GET ``url`` with ``headers`` and return the decoded JSON body."""
        ...


@runtime_checkable
class ProviderCostClient(Protocol):
    """A provider cost API client: fetch the authoritative daily billed totals."""

    def fetch_daily_costs(self, *, day: str) -> tuple[BilledTotal, ...]:
        """Return the authoritative billed totals for ``day`` (YYYY-MM-DD)."""
        ...


def _to_decimal(raw: object, *, provider: str) -> Decimal:
    """Coerce a cost-API amount string/number to exact Decimal, or raise typed."""
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError) as exc:
        raise ProviderCostApiError(
            f"{provider} cost API returned a non-decimal amount {raw!r}"
        ) from exc


def _require_admin_key(key: str, *, provider: str) -> str:
    """Validate the admin-key precondition without ever logging the key."""
    if not key or not key.strip():
        raise AdminKeyRequiredError(f"{provider} cost API requires an Admin key; none was supplied")
    return key


def _rows(payload: object, *, provider: str) -> list[dict[str, object]]:
    """Extract the ``data`` array of row dicts from a cost-API payload, or raise typed."""
    if not isinstance(payload, dict):
        raise ProviderCostApiError(f"{provider} cost API payload missing 'data' array")
    body = cast("dict[str, object]", payload)
    if "data" not in body:
        raise ProviderCostApiError(f"{provider} cost API payload missing 'data' array")
    data = body["data"]
    if not isinstance(data, list):
        raise ProviderCostApiError(f"{provider} cost API 'data' is not a list")
    items = cast("list[object]", data)
    rows: list[dict[str, object]] = []
    for item in items:
        if isinstance(item, dict):
            row = cast("dict[object, object]", item)
            rows.append({str(k): v for k, v in row.items()})
    return rows


def _openai_amount(row: dict[str, object]) -> object:
    """Pull the OpenAI Costs amount value (``{amount: {value: ...}}`` or scalar)."""
    amount: object = row.get("amount")
    if isinstance(amount, dict):
        return cast("dict[str, object]", amount).get("value")
    return amount


class OpenAICostClient:
    """OpenAI Costs client (1-day granularity); admin-key gated, key never logged."""

    __slots__ = ("_admin_key", "_transport")

    _BASE_URL = "https://api.openai.com/v1/organization/costs"

    def __init__(self, *, transport: CostApiTransport, admin_key: str) -> None:
        """Build the client, validating the admin-key precondition up front."""
        self._admin_key = _require_admin_key(admin_key, provider="openai")
        self._transport = transport

    @override
    def __repr__(self) -> str:
        """A key-free repr (the admin key is never exposed)."""
        return "OpenAICostClient(transport=..., admin_key=<redacted>)"

    def fetch_daily_costs(self, *, day: str) -> tuple[BilledTotal, ...]:
        """Fetch and normalise OpenAI Costs rows for ``day`` into BilledTotal."""
        _log.debug("fetching openai costs for day=%s", day)  # no key in the message
        headers = {"Authorization": f"Bearer {self._admin_key}"}
        payload = self._transport.get(f"{self._BASE_URL}?date={day}", headers)
        totals: list[BilledTotal] = []
        for row in _rows(payload, provider="openai"):
            totals.append(
                BilledTotal(
                    provider="openai",
                    project=str(row.get("project_id", "")),
                    model=str(row.get("model", "")),
                    token_class=str(row.get("line_item", "")),
                    day=day,
                    billed_usd=_to_decimal(_openai_amount(row), provider="openai"),
                )
            )
        return tuple(totals)


class AnthropicCostClient:
    """Anthropic cost_report + usage_report client; admin-key gated, key never logged."""

    __slots__ = ("_admin_key", "_transport")

    _BASE_URL = "https://api.anthropic.com/v1/organizations/cost_report"

    def __init__(self, *, transport: CostApiTransport, admin_key: str) -> None:
        """Build the client, validating the admin-key precondition up front."""
        self._admin_key = _require_admin_key(admin_key, provider="anthropic")
        self._transport = transport

    @override
    def __repr__(self) -> str:
        """A key-free repr (the admin key is never exposed)."""
        return "AnthropicCostClient(transport=..., admin_key=<redacted>)"

    def fetch_daily_costs(self, *, day: str) -> tuple[BilledTotal, ...]:
        """Fetch and normalise Anthropic cost_report rows for ``day`` into BilledTotal."""
        _log.debug("fetching anthropic cost_report for day=%s", day)  # no key in the message
        headers = {"x-api-key": self._admin_key, "anthropic-version": "2023-06-01"}
        payload = self._transport.get(f"{self._BASE_URL}?starting_at={day}", headers)
        totals: list[BilledTotal] = []
        for row in _rows(payload, provider="anthropic"):
            totals.append(
                BilledTotal(
                    provider="anthropic",
                    project=str(row.get("workspace_id", "")),
                    model=str(row.get("model", "")),
                    token_class=str(row.get("token_class", "")),
                    day=day,
                    billed_usd=_to_decimal(row.get("cost_usd"), provider="anthropic"),
                )
            )
        return tuple(totals)


__all__ = [
    "AdminKeyRequiredError",
    "AnthropicCostClient",
    "BilledTotal",
    "CostApiTransport",
    "OpenAICostClient",
    "ProviderCostApiError",
    "ProviderCostClient",
]
