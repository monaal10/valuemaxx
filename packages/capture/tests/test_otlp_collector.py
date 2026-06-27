"""LIVE-TEST RATCHET — the OTLP/HTTP collector decode (POST /v1/traces).

Caught by the live vibechk integration test: the TS SDK's `OTLPTraceExporter`
posts a standard OTLP-JSON `ExportTraceServiceRequest` to `<endpoint>/v1/traces`,
but the backend had no collector to decode that wire format — only a pre-shaped
`{tenant_id, attributes}` JSON route. So a real SDK span never reached a CostEvent
(404 on /v1/traces). These tests lock in the OTLP-JSON -> flat-attribute decode
that bridges the SDK exporter to `span_to_cost_event`.

The subtle trap covered here: OTLP-JSON encodes integer attribute values as
*strings* (`{"intValue": "100"}`), so a naive decode yields the string "100" and
`span_to_cost_event` reads 0 tokens. The decoder must coerce AnyValue to native.
"""

from __future__ import annotations

from valuemaxx.capture.otlp.collector import otlp_json_to_attribute_maps

# Exactly the shape the real @opentelemetry/exporter-trace-otlp-http emits
# (captured empirically from the built TS SDK exporter): note intValue is a STRING.
_REAL_OTLP_JSON: dict[str, object] = {
    "resourceSpans": [
        {
            "resource": {
                "attributes": [{"key": "service.name", "value": {"stringValue": "probe"}}]
            },
            "scopeSpans": [
                {
                    "scope": {"name": "valuemaxx"},
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
                                    "key": "gen_ai.usage.input_tokens",
                                    "value": {"intValue": "100"},
                                },
                                {
                                    "key": "gen_ai.usage.output_tokens",
                                    "value": {"intValue": "50"},
                                },
                                {"key": "ai_margin.run_id", "value": {"stringValue": "run-7"}},
                                {"key": "ai_margin.attempt_id", "value": {"stringValue": "att-1"}},
                                {"key": "ai_margin.is_streaming", "value": {"boolValue": False}},
                                {"key": "ai_margin.cost_usd", "value": {"doubleValue": 0.0125}},
                            ],
                        }
                    ],
                }
            ],
        }
    ]
}


def test_decode_flattens_spans_to_native_attribute_maps() -> None:
    """One OTLP span -> one flat attribute dict with NATIVE python values."""
    maps = otlp_json_to_attribute_maps(_REAL_OTLP_JSON)
    assert len(maps) == 1
    attrs = maps[0]
    # strings decode as str
    assert attrs["gen_ai.system"] == "anthropic"
    assert attrs["gen_ai.request.model"] == "claude-3-5-haiku"
    # the trap: OTLP intValue is wire-encoded as a STRING and must become a real int
    assert attrs["gen_ai.usage.input_tokens"] == 100
    assert isinstance(attrs["gen_ai.usage.input_tokens"], int)
    assert attrs["gen_ai.usage.output_tokens"] == 50
    # bool/double round-trip to native python
    assert attrs["ai_margin.is_streaming"] is False
    assert attrs["ai_margin.cost_usd"] == 0.0125
    assert attrs["ai_margin.run_id"] == "run-7"
    assert attrs["ai_margin.attempt_id"] == "att-1"


def test_decode_handles_multiple_spans_across_scopes_and_resources() -> None:
    """Every span across all resourceSpans/scopeSpans becomes its own attribute map."""
    body: dict[str, object] = {
        "resourceSpans": [
            {
                "scopeSpans": [
                    {"spans": [{"attributes": [{"key": "a", "value": {"intValue": "1"}}]}]},
                    {"spans": [{"attributes": [{"key": "b", "value": {"intValue": "2"}}]}]},
                ]
            },
            {
                "scopeSpans": [
                    {"spans": [{"attributes": [{"key": "c", "value": {"intValue": "3"}}]}]}
                ]
            },
        ]
    }
    maps = otlp_json_to_attribute_maps(body)
    assert list(maps) == [{"a": 1}, {"b": 2}, {"c": 3}]


def test_decode_tolerates_empty_and_malformed_shapes() -> None:
    """Missing keys never raise — a malformed body yields no attribute maps."""
    empty: dict[str, object] = {}
    no_resources: dict[str, object] = {"resourceSpans": []}
    bare_rs: dict[str, object] = {"resourceSpans": [{}]}
    bare_scope: dict[str, object] = {"resourceSpans": [{"scopeSpans": [{}]}]}
    bare_span: dict[str, object] = {"resourceSpans": [{"scopeSpans": [{"spans": [{}]}]}]}
    assert otlp_json_to_attribute_maps(empty) == []
    assert otlp_json_to_attribute_maps(no_resources) == []
    assert otlp_json_to_attribute_maps(bare_rs) == []
    assert otlp_json_to_attribute_maps(bare_scope) == []
    # a span with no attributes -> an empty map, still one entry
    assert otlp_json_to_attribute_maps(bare_span) == [{}]


def test_decode_ignores_unknown_anyvalue_kinds() -> None:
    """An AnyValue kind we don't map (arrayValue/kvlistValue) is skipped, not crashed."""
    body: dict[str, object] = {
        "resourceSpans": [
            {
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "attributes": [
                                    {"key": "ok", "value": {"stringValue": "yes"}},
                                    {"key": "arr", "value": {"arrayValue": {"values": []}}},
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    }
    assert otlp_json_to_attribute_maps(body) == [{"ok": "yes"}]
