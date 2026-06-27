"""Ingest-side adapter for framework-specific span attribute keys (read-only).

Different LLM frameworks emit different OTel span attributes. valuemaxx's canonical
wire contract is the ``gen_ai.*`` + ``ai_margin.*`` key set in :mod:`semconv` (which
both SDKs *emit* and which lives in the cross-language ``ALL_KEYS`` fixture). But when
valuemaxx ingests spans a third-party framework produced — e.g. the **Vercel AI SDK**
via ``experimental_telemetry`` — those spans use the framework's own keys.

This module maps the framework keys onto the canonical token classes **on ingest
only**. It is deliberately NOT part of ``ALL_KEYS``: valuemaxx does not emit these
keys, and adding them would wrongly imply a cross-language emission contract.

Vercel AI SDK (``ai`` v5/v6) — verified against ``ai@6.0.168`` on a real repo. Token
usage lives under ``ai.usage.*`` on the ``ai.generateText.doGenerate`` span; the v6
``inputTokens`` is the TOTAL input (cached + uncached), with cache read/write as
subsets under ``inputTokenDetails`` — exactly the ``total_input`` +
cache-subset shape :meth:`TokenVector.from_provider` expects:

* ``ai.usage.inputTokens``                          -> total input
* ``ai.usage.outputTokens``                         -> output
* ``ai.usage.inputTokenDetails.cacheReadTokens``    -> cache read
* ``ai.usage.inputTokenDetails.cacheWriteTokens``   -> cache write (mapped to the 5m class)
* ``ai.usage.outputTokenDetails.reasoningTokens``   -> reasoning
  (``ai.usage.reasoningTokens`` is the v5 fallback)

``gen_ai.system`` and ``gen_ai.request.model`` already match the canonical keys, so
provider/model need no aliasing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from valuemaxx.capture.otlp import semconv

if TYPE_CHECKING:
    from collections.abc import Mapping

# Framework token keys -> the canonical semconv token key they stand in for. Within a
# class the tuple is read precedence (first present wins); applied only when the
# canonical key is absent (see ``apply_vendor_token_aliases``). One flat table spans
# every supported framework — the keys are distinct enough not to collide:
#
#   * Vercel AI SDK (``ai`` v5/v6): ``ai.usage.*`` on ai.generateText.doGenerate.
#   * LangChain / OpenLLMetry / OpenInference: LangChain's OTel exporters emit the
#     standard GenAI usage convention with the *older* token names
#     (``gen_ai.usage.prompt_tokens`` / ``completion_tokens``), and OpenInference uses
#     ``llm.token_count.{prompt,completion,...}``. Both are mapped here.
#   * Direct OpenAI/Anthropic via OpenLLMetry also use the ``gen_ai.usage.*_tokens``
#     prompt/completion spelling, covered by the same LangChain aliases.
_VENDOR_TOKEN_ALIASES: Final[Mapping[str, tuple[str, ...]]] = {
    semconv.GEN_AI_USAGE_INPUT_TOKENS: (
        "ai.usage.inputTokens",  # Vercel AI SDK
        "gen_ai.usage.prompt_tokens",  # LangChain / OpenLLMetry (older GenAI spelling)
        "llm.token_count.prompt",  # OpenInference (LangChain/LlamaIndex)
    ),
    semconv.GEN_AI_USAGE_OUTPUT_TOKENS: (
        "ai.usage.outputTokens",
        "gen_ai.usage.completion_tokens",
        "llm.token_count.completion",
    ),
    semconv.AI_MARGIN_CACHE_READ: (
        "ai.usage.inputTokenDetails.cacheReadTokens",
        "ai.usage.cachedInputTokens",
        "gen_ai.usage.cache_read_input_tokens",  # Anthropic-via-OpenLLMetry
        "llm.token_count.prompt_details.cache_read",  # OpenInference
    ),
    semconv.AI_MARGIN_CACHE_WRITE_5M: (
        "ai.usage.inputTokenDetails.cacheWriteTokens",
        "gen_ai.usage.cache_creation_input_tokens",  # Anthropic-via-OpenLLMetry
    ),
    semconv.AI_MARGIN_REASONING: (
        "ai.usage.outputTokenDetails.reasoningTokens",
        "ai.usage.reasoningTokens",
        "llm.token_count.completion_details.reasoning",  # OpenInference
    ),
    # provider + model — needed to price. Vercel + OpenLLMetry already use the canonical
    # gen_ai.system / gen_ai.request.model; OpenInference (LangChain/LlamaIndex) does not.
    semconv.GEN_AI_SYSTEM: (
        "llm.system",  # OpenInference
        "llm.provider",  # OpenInference (some versions)
    ),
    semconv.GEN_AI_REQUEST_MODEL: (
        "llm.model_name",  # OpenInference
        "gen_ai.response.model",  # GenAI semconv response-side fallback
    ),
}


# The AI SDK reports `gen_ai.system` as `<vendor>.<api>` (e.g. "anthropic.messages",
# "openai.chat", "google.generative-ai"). The vendor prefix is what pricebooks key on, so
# we strip the API suffix on ingest. Only these known vendors are collapsed — an unknown
# dotted provider is left intact (we don't guess).
_KNOWN_VENDORS: Final[frozenset[str]] = frozenset({"anthropic", "openai", "google", "azure"})


def normalize_provider(provider: str) -> str:
    """Collapse an AI-SDK ``<vendor>.<api>`` provider string to its bare vendor.

    ``"anthropic.messages" -> "anthropic"``, ``"openai.chat" -> "openai"``,
    ``"google.generative-ai" -> "google"``. A bare vendor, or any provider whose prefix is
    not a known vendor (a gateway alias, ``openrouter``, …), is returned unchanged — we
    normalize only what we recognize, never guess.
    """
    head, _, _tail = provider.partition(".")
    if _tail and head in _KNOWN_VENDORS:
        return head
    return provider


def apply_vendor_token_aliases(attrs: Mapping[str, object]) -> dict[str, object]:
    """Return a copy of ``attrs`` with framework keys filled into canonical keys.

    For each canonical key absent from ``attrs``, the first present vendor alias
    supplies its value. Canonical keys always win — a span that already carries the
    real ``gen_ai.*`` key is never overridden. Other keys (ids, flags) pass through
    untouched. Pure and total: never raises, never mutates the input.

    Covers token usage, provider, and model across the Vercel AI SDK, LangChain
    (OpenLLMetry's GenAI spelling), and OpenInference (LangChain/LlamaIndex) — see the
    alias table for the per-framework key list.
    """
    merged = dict(attrs)
    for canonical, aliases in _VENDOR_TOKEN_ALIASES.items():
        if canonical in merged:
            continue  # canonical key present -> never override with a vendor alias
        for alias in aliases:
            if alias in attrs:
                merged[canonical] = attrs[alias]
                break
    return merged


__all__ = ["apply_vendor_token_aliases", "normalize_provider"]
