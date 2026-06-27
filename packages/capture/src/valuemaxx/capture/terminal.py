"""PG3 — streaming terminal-value capture (the 2x fix, §5.2).

Streaming usage is reported incrementally, but cost must be priced from the
**terminal** values, never the running deltas. Two provider accumulators encode
the exact rules:

**Anthropic** (:class:`AnthropicStreamAccumulator`):
  * ``output`` is taken from ``message_delta.usage.output_tokens`` as the
    *cumulative terminal* value — each delta OVERWRITES, we never sum them;
  * cache tokens are read from ``message_start`` exactly ONCE — summing the cache
    fields that appear in both ``message_start`` and ``message_delta`` is the
    ``@langchain/anthropic`` 2x cache double-count bug, which this avoids;
  * the 5m/1h cache-write split comes from the nested
    ``cache_creation.{ephemeral_5m,ephemeral_1h}_input_tokens`` fields;
  * ``reasoning`` is DERIVED by counting ``thinking`` content blocks.

**OpenAI** (:class:`OpenAIStreamAccumulator`):
  * usage lives in the FINAL chunk only and REQUIRES ``stream_options.include_usage``;
  * if usage never arrives (include_usage off, or a cancelled stream), we flag
    ``partial_recovered`` rather than logging a silent zero.

A cancelled stream recovers whatever terminal value it has and flags
``partial_recovered`` — never a silent zero (§5.2).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from valuemaxx.capture.patch import AttemptObservation
from valuemaxx.core.tokens import TokenVector

if TYPE_CHECKING:
    from collections.abc import Mapping


def _as_mapping(value: object) -> Mapping[str, object]:
    """Narrow an untyped event payload to a string-keyed mapping (or empty)."""
    if isinstance(value, dict):
        return cast("Mapping[str, object]", value)
    return {}


def _as_int(value: object) -> int:
    """Coerce a usage field to a non-negative int (a missing/None field is 0)."""
    if isinstance(value, bool):  # guard: bool is an int subclass we never want here
        return 0
    if isinstance(value, int):
        return max(value, 0)
    return 0


class AnthropicStreamAccumulator:
    """Accumulate an Anthropic streaming response to TERMINAL token values (§5.2)."""

    def __init__(self) -> None:
        self._cache_read = 0
        self._cache_write_5m = 0
        self._cache_write_1h = 0
        self._input_uncached = 0
        self._output_terminal = 0
        self._thinking_blocks = 0
        self._saw_message_start = False
        self._cancelled = False

    def observe(self, event: Mapping[str, object]) -> None:
        """Fold one streaming event into the accumulator (idempotent on cache fields)."""
        event_type = event.get("type")
        if event_type == "message_start":
            self._observe_message_start(event)
        elif event_type == "message_delta":
            self._observe_message_delta(event)
        elif event_type == "content_block_start":
            block = _as_mapping(event.get("content_block"))
            if block.get("type") == "thinking":
                self._thinking_blocks += 1

    def _observe_message_start(self, event: Mapping[str, object]) -> None:
        # cache tokens are read here ONCE; later events never re-add them (the 2x fix).
        self._saw_message_start = True
        usage = _as_mapping(_as_mapping(event.get("message")).get("usage"))
        self._input_uncached = _as_int(usage.get("input_tokens"))
        self._cache_read = _as_int(usage.get("cache_read_input_tokens"))
        cache_creation = _as_mapping(usage.get("cache_creation"))
        self._cache_write_5m = _as_int(cache_creation.get("ephemeral_5m_input_tokens"))
        self._cache_write_1h = _as_int(cache_creation.get("ephemeral_1h_input_tokens"))
        # message_start may already carry an output_tokens; treat it as the first terminal.
        self._output_terminal = _as_int(usage.get("output_tokens"))

    def _observe_message_delta(self, event: Mapping[str, object]) -> None:
        # output_tokens here is the CUMULATIVE terminal value — OVERWRITE, never sum.
        usage = _as_mapping(event.get("usage"))
        if "output_tokens" in usage:
            self._output_terminal = _as_int(usage.get("output_tokens"))

    def mark_cancelled(self) -> None:
        """Record that the stream was cancelled before its terminal message_stop."""
        self._cancelled = True

    def finalize(self) -> TokenVector:
        """Build the terminal :class:`TokenVector` (output >= reasoning by construction)."""
        # reasoning is embedded within output; ensure output covers the derived count.
        output = max(self._output_terminal, self._thinking_blocks)
        return TokenVector(
            input_uncached=self._input_uncached,
            cache_read=self._cache_read,
            cache_write_5m=self._cache_write_5m,
            cache_write_1h=self._cache_write_1h,
            output=output,
            reasoning=self._thinking_blocks,
        )

    def finalize_observation(self, *, provider: str, model: str) -> AttemptObservation:
        """Build the :class:`AttemptObservation` for the patch/emit path."""
        partial = self._cancelled or not self._saw_message_start
        return AttemptObservation(
            provider=provider,
            model=model,
            tokens=self.finalize(),
            is_streaming=True,
            partial_recovered=partial,
        )


class OpenAIStreamAccumulator:
    """Accumulate an OpenAI streaming response; usage is in the FINAL chunk only (§5.2).

    Args:
        include_usage: whether ``stream_options.include_usage`` was set. When False,
            usage never arrives and the stream is flagged ``partial_recovered`` rather
            than reporting a silent zero.
    """

    def __init__(self, *, include_usage: bool) -> None:
        self._include_usage = include_usage
        self._input_total = 0
        self._cache_read = 0
        self._output = 0
        self._saw_usage = False
        self._cancelled = False

    def observe(self, chunk: Mapping[str, object]) -> None:
        """Fold one streaming chunk; only the final chunk carries usage."""
        usage = chunk.get("usage")
        if not isinstance(usage, dict):
            return
        usage_map = cast("Mapping[str, object]", usage)
        self._saw_usage = True
        self._input_total = _as_int(usage_map.get("prompt_tokens"))
        details = _as_mapping(usage_map.get("prompt_tokens_details"))
        self._cache_read = _as_int(details.get("cached_tokens"))
        self._output = _as_int(usage_map.get("completion_tokens"))

    def mark_cancelled(self) -> None:
        """Record that the stream was cancelled before the final usage chunk."""
        self._cancelled = True

    def finalize(self) -> TokenVector:
        """Build the terminal :class:`TokenVector` (uncached = prompt - cached)."""
        # OpenAI has no distinct cache-write class; uncached input is the remainder.
        cache_read = min(self._cache_read, self._input_total)
        return TokenVector(
            input_uncached=self._input_total - cache_read,
            cache_read=cache_read,
            cache_write_5m=0,
            cache_write_1h=0,
            output=self._output,
            reasoning=0,
        )

    def finalize_observation(self, *, provider: str, model: str) -> AttemptObservation:
        """Build the :class:`AttemptObservation`; flag partial if usage never arrived."""
        partial = self._cancelled or not self._saw_usage
        return AttemptObservation(
            provider=provider,
            model=model,
            tokens=self.finalize(),
            is_streaming=True,
            partial_recovered=partial,
        )


__all__ = ["AnthropicStreamAccumulator", "OpenAIStreamAccumulator"]
