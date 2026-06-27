"""The SINGLE source of truth for every OTLP attribute key (§5.2, H3).

Every wire key the capture path emits or ingests is a module constant here — the
standard OpenTelemetry GenAI ``gen_ai.*`` keys plus the valuemaxx ``ai_margin.*``
extensions for the token classes, ids, provenance, and flags that the standard
semconv does not model. Nothing else in the codebase may re-type one of these
literals (asserted by the ``otlp_ingest`` AST test and the wire-contract parity
rule), and the TypeScript SDK consumes the generated fixture so the two languages
share one key set.

``ALL_KEYS`` is the authoritative set; ``generate_semconv_fixture`` writes
``{"keys": sorted(ALL_KEYS)}`` to a JSON file — the byte-for-byte cross-language
contract checked by ``git diff --exit-code`` in CI.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

# --- standard OpenTelemetry GenAI keys (gen_ai.*) ----------------------------
GEN_AI_SYSTEM = "gen_ai.system"
"""The provider/system (e.g. ``anthropic``, ``openai``)."""

GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
"""The model id requested."""

GEN_AI_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
"""Total input tokens (the uncached + cached input slices live in extensions)."""

GEN_AI_USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
"""Total output tokens (terminal value for streaming)."""

# --- valuemaxx extensions (ai_margin.*) --------------------------------------
AI_MARGIN_CACHE_READ = "ai_margin.usage.cache_read_tokens"
"""Cache-read input tokens (priced at the discounted cache-read rate)."""

AI_MARGIN_CACHE_WRITE_5M = "ai_margin.usage.cache_write_5m_tokens"
"""5-minute cache-write input tokens (distinct price from the 1h class)."""

AI_MARGIN_CACHE_WRITE_1H = "ai_margin.usage.cache_write_1h_tokens"
"""1-hour cache-write input tokens (distinct price from the 5m class)."""

AI_MARGIN_REASONING = "ai_margin.usage.reasoning_tokens"
"""Reasoning tokens — derived (thinking-block count), embedded within output."""

AI_MARGIN_RUN_ID = "ai_margin.run_id"
"""The agent run id this attempt belongs to."""

AI_MARGIN_ATTEMPT_ID = "ai_margin.attempt_id"
"""The per-HTTP-attempt id (part of the (run_id, attempt_id) dedup key)."""

AI_MARGIN_TENANT_ID = "ai_margin.tenant_id"
"""The tenant scope (required; ingest also takes it as a mandatory param)."""

AI_MARGIN_PROVENANCE = "ai_margin.provenance"
"""The cost-provenance honesty axis value (measured / provider_reconciled / ...)."""

AI_MARGIN_CAPTURE_GRANULARITY = "ai_margin.capture_granularity"
"""Whether this is per_attempt or the degraded per_call fallback."""

AI_MARGIN_COST_USD = "ai_margin.cost_usd"
"""An authoritative inline cost (e.g. gateway usage.cost); used as-is when present."""

AI_MARGIN_IS_STREAMING = "ai_margin.is_streaming"
"""Whether the attempt was a streaming response."""

AI_MARGIN_PARTIAL_RECOVERED = "ai_margin.partial_recovered"
"""Whether usage was only partially recovered (cancelled / missing include_usage)."""

ALL_KEYS: frozenset[str] = frozenset(
    {
        GEN_AI_SYSTEM,
        GEN_AI_REQUEST_MODEL,
        GEN_AI_USAGE_INPUT_TOKENS,
        GEN_AI_USAGE_OUTPUT_TOKENS,
        AI_MARGIN_CACHE_READ,
        AI_MARGIN_CACHE_WRITE_5M,
        AI_MARGIN_CACHE_WRITE_1H,
        AI_MARGIN_REASONING,
        AI_MARGIN_RUN_ID,
        AI_MARGIN_ATTEMPT_ID,
        AI_MARGIN_TENANT_ID,
        AI_MARGIN_PROVENANCE,
        AI_MARGIN_CAPTURE_GRANULARITY,
        AI_MARGIN_COST_USD,
        AI_MARGIN_IS_STREAMING,
        AI_MARGIN_PARTIAL_RECOVERED,
    }
)
"""The authoritative set of every OTLP key the capture path uses."""


def generate_semconv_fixture(path: Path) -> None:
    """Write the cross-language key fixture ``{"keys": sorted(ALL_KEYS)}`` to ``path``.

    CI regenerates this and runs ``git diff --exit-code`` so any drift between the
    constants here and the committed fixture (and the TypeScript copy) fails the
    build before the TS job runs (H3).
    """
    payload = {"keys": sorted(ALL_KEYS)}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


__all__ = [
    "AI_MARGIN_ATTEMPT_ID",
    "AI_MARGIN_CACHE_READ",
    "AI_MARGIN_CACHE_WRITE_1H",
    "AI_MARGIN_CACHE_WRITE_5M",
    "AI_MARGIN_CAPTURE_GRANULARITY",
    "AI_MARGIN_COST_USD",
    "AI_MARGIN_IS_STREAMING",
    "AI_MARGIN_PARTIAL_RECOVERED",
    "AI_MARGIN_PROVENANCE",
    "AI_MARGIN_REASONING",
    "AI_MARGIN_RUN_ID",
    "AI_MARGIN_TENANT_ID",
    "ALL_KEYS",
    "GEN_AI_REQUEST_MODEL",
    "GEN_AI_SYSTEM",
    "GEN_AI_USAGE_INPUT_TOKENS",
    "GEN_AI_USAGE_OUTPUT_TOKENS",
    "generate_semconv_fixture",
]
