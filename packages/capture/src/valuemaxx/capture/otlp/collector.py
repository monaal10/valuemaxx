"""Decode a standard OTLP/HTTP ``ExportTraceServiceRequest`` (JSON) into flat
attribute maps — the wire bridge between the SDK's OTLP exporter and
:func:`~valuemaxx.capture.otlp.otlp_ingest.span_to_cost_event`.

Why this exists (live-test finding): the TS SDK's
``@opentelemetry/exporter-trace-otlp-http`` posts a real OTLP-JSON body to
``<endpoint>/v1/traces``::

    {"resourceSpans":[{"scopeSpans":[{"spans":[
        {"name":"ai.generateText","attributes":[
            {"key":"gen_ai.system","value":{"stringValue":"anthropic"}},
            {"key":"gen_ai.usage.input_tokens","value":{"intValue":"100"}}]}]}]}]}

``span_to_cost_event`` consumes a *flat* ``Mapping[str, object]`` of native python
values, so this module flattens ``resourceSpans -> scopeSpans -> spans ->
attributes`` and coerces each OTLP ``AnyValue`` to a native value.

The decode trap covered by the tests: OTLP-JSON encodes ``intValue`` as a **string**
(``{"intValue": "100"}``). A naive pass-through leaves the value as ``"100"`` and the
token reader sees 0 — so this decoder must coerce it to a real ``int``. The decoder
is total: any missing/extra/unknown shape is skipped, never raised, so a partially
malformed batch still yields the spans it can decode (fail-open, H9).
"""

from __future__ import annotations

from typing import cast


def _as_obj_dict(value: object) -> dict[str, object] | None:
    """Narrow ``object`` to a ``dict[str, object]`` (the only JSON-object shape we walk)."""
    if isinstance(value, dict):
        return cast("dict[str, object]", value)
    return None


def _as_obj_list(value: object) -> list[object] | None:
    """Narrow ``object`` to a ``list[object]`` (a JSON array of nested nodes)."""
    if isinstance(value, list):
        return cast("list[object]", value)
    return None


def _coerce_any_value(value: object) -> object | None:
    """Coerce one OTLP ``AnyValue`` object to a native python value.

    Returns ``None`` for an AnyValue kind we don't map (``arrayValue``/``kvlistValue``/
    ``bytesValue``) so the caller drops it rather than storing an opaque shape. Note
    OTLP-JSON encodes ``intValue`` as a decimal *string*; we parse it back to ``int``.
    """
    av = _as_obj_dict(value)
    if av is None:
        return None
    if "stringValue" in av:
        sv = av["stringValue"]
        return sv if isinstance(sv, str) else None
    if "intValue" in av:
        iv = av["intValue"]
        # OTLP-JSON int is a string; some encoders emit a JSON number — accept both.
        # (bool is an int subclass, so guard it out: an intValue is never a bool here.)
        if isinstance(iv, bool):
            return None
        if isinstance(iv, int):
            return iv
        if isinstance(iv, str):
            try:
                return int(iv)
            except ValueError:
                return None
        return None
    if "doubleValue" in av:
        dv = av["doubleValue"]
        if isinstance(dv, bool):
            return None
        return dv if isinstance(dv, (int, float)) else None
    if "boolValue" in av:
        bv = av["boolValue"]
        return bv if isinstance(bv, bool) else None
    # arrayValue / kvlistValue / bytesValue and anything else: not a scalar attribute.
    return None


def _attributes_to_map(attributes: object) -> dict[str, object]:
    """Flatten an OTLP ``attributes`` list (``[{key, value:{...}}]``) to a native dict."""
    out: dict[str, object] = {}
    attr_list = _as_obj_list(attributes)
    if attr_list is None:
        return out
    for raw_attr in attr_list:
        attr = _as_obj_dict(raw_attr)
        if attr is None:
            continue
        key = attr.get("key")
        if not isinstance(key, str):
            continue
        coerced = _coerce_any_value(attr.get("value"))
        if coerced is not None:
            out[key] = coerced
    return out


def otlp_json_to_attribute_maps(body: object) -> list[dict[str, object]]:
    """Decode an OTLP-JSON ``ExportTraceServiceRequest`` to one attribute map per span.

    Walks ``resourceSpans[].scopeSpans[].spans[].attributes[]`` and returns a flat
    native-valued dict for every span, in document order. Total: any missing or
    malformed level is skipped (never raised), so a partially valid batch still
    yields the spans it can decode.
    """
    maps: list[dict[str, object]] = []
    root = _as_obj_dict(body)
    if root is None:
        return maps
    resource_spans = _as_obj_list(root.get("resourceSpans"))
    if resource_spans is None:
        return maps
    for raw_rs in resource_spans:
        rs = _as_obj_dict(raw_rs)
        if rs is None:
            continue
        scope_spans = _as_obj_list(rs.get("scopeSpans"))
        if scope_spans is None:
            continue
        for raw_ss in scope_spans:
            ss = _as_obj_dict(raw_ss)
            if ss is None:
                continue
            spans = _as_obj_list(ss.get("spans"))
            if spans is None:
                continue
            for raw_span in spans:
                span = _as_obj_dict(raw_span)
                if span is None:
                    continue
                maps.append(_attributes_to_map(span.get("attributes")))
    return maps


__all__ = ["otlp_json_to_attribute_maps"]
