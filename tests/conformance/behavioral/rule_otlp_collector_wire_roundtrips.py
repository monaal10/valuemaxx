"""otlp_collector_wire_roundtrips — the SDK's OTLP exporter wire reaches a CostEvent.

Live-test ratchet (owner CAPTURE/API). The TS SDK ships spans via a standard OTLP
exporter that POSTs an ``ExportTraceServiceRequest`` (OTLP-JSON) to
``<endpoint>/v1/traces`` with the per-tenant key in ``x-valuemaxx-ingest-key``. The
backend MUST expose that collector route and decode the real wire format (including
the trap that OTLP-JSON encodes ``intValue`` as a *string*) into a persisted, queryable
CostEvent. Before this rule, ``/v1/traces`` 404'd and the two halves of the product
could not connect.

``flags_violation`` inspects an outcome record ``{status, numerator}`` from posting a
real OTLP-JSON span and querying the cost back. It flags iff the route did not accept
the span (non-200) or the wrong cost came back (token/int decode broke). The negative
fixture is a 404 (route missing) — the exact pre-fix state.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Protocol, cast

from tests.conformance.rulebase import Rule, RuleKind

if TYPE_CHECKING:
    import httpx

_EXPECTED_COST = Decimal("0.0125")


class _HttpClient(Protocol):
    """A precisely-typed view of the otherwise pyright-opaque starlette TestClient."""

    def post(
        self,
        url: str,
        *,
        json: object | None = ...,
        headers: dict[str, str] | None = ...,
    ) -> httpx.Response: ...


def _flags(subject: object) -> bool:
    """subject: {'status': int, 'numerator': str|None}. Flag iff not accepted or wrong cost."""
    assert isinstance(subject, dict)
    record = cast("dict[str, object]", subject)
    status = record.get("status")
    if status != 200:
        return True
    numerator = record.get("numerator")
    if not isinstance(numerator, str):
        return True
    return Decimal(numerator) != _EXPECTED_COST


def _negative_fixture() -> object:
    # the pre-fix state: /v1/traces did not exist, so the exporter got a 404.
    return {"status": 404, "numerator": None}


def _foundation_subject() -> object:
    """Boot the real app, POST a real OTLP-JSON span to /v1/traces, query the cost back."""
    from pathlib import Path
    from tempfile import TemporaryDirectory
    from uuid import uuid4

    from fastapi.testclient import TestClient
    from valuemaxx.server.app import create_app
    from valuemaxx.server.settings import ServerSettings

    ingest_key = "conformance-ingest-key"
    tenant = str(uuid4())
    otlp_body: dict[str, object] = {
        "resourceSpans": [
            {
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "name": "ai.generateText",
                                "attributes": [
                                    {"key": "gen_ai.system", "value": {"stringValue": "anthropic"}},
                                    {
                                        "key": "gen_ai.request.model",
                                        "value": {"stringValue": "claude-3-5-haiku"},
                                    },
                                    {
                                        # intValue is STRING-encoded on the wire (the decode trap)
                                        "key": "gen_ai.usage.input_tokens",
                                        "value": {"intValue": "1000"},
                                    },
                                    {
                                        "key": "gen_ai.usage.output_tokens",
                                        "value": {"intValue": "250"},
                                    },
                                    {"key": "ai_margin.run_id", "value": {"stringValue": "c-run"}},
                                    {
                                        "key": "ai_margin.attempt_id",
                                        "value": {"stringValue": "c-att"},
                                    },
                                    {
                                        "key": "ai_margin.cost_usd",
                                        "value": {"stringValue": str(_EXPECTED_COST)},
                                    },
                                ],
                            }
                        ]
                    }
                ]
            }
        ]
    }
    metric_def: dict[str, object] = {
        "name": "cost_per_outcome",
        "numerator": "total_cost_usd",
        "denominator": "verified_outcome_count",
        "filters": {},
        "group_by": [],
    }

    with TemporaryDirectory() as tmp:
        settings = ServerSettings(
            database_url=f"sqlite+aiosqlite:///{Path(tmp) / 'conf.db'}",
            ingest_keys={ingest_key: tenant},
            webhook_secret="conformance-secret",
        )
        with TestClient(create_app(settings)) as raw_client:
            client = cast("_HttpClient", raw_client)
            resp = client.post(
                "/v1/traces", json=otlp_body, headers={"x-valuemaxx-ingest-key": ingest_key}
            )
            if resp.status_code != 200:
                return {"status": resp.status_code, "numerator": None}
            metric = client.post("/run_metric", json=metric_def, headers={"X-API-Key": ingest_key})
            cells = cast("list[dict[str, object]]", metric.json().get("cells", []))
            numerator = cells[0]["numerator_value"] if cells else None
            return {"status": metric.status_code, "numerator": numerator}


RULE = Rule(
    name="otlp_collector_wire_roundtrips",
    kind=RuleKind.BEHAVIORAL,
    green_now=True,
    owner_task="capture",
    flags_violation=_flags,
    negative_fixture=_negative_fixture,
    foundation_subject=_foundation_subject,
)
