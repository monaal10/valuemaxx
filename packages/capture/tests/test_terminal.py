"""PG3 — streaming terminal-value capture (the 2x fix, §5.2).

Anthropic: output is taken TERMINALLY from ``message_delta.usage.output_tokens``
(overwrite, never sum the deltas); cache tokens come from ``message_start`` ONCE
(summing them from both message_start and message_delta is the @langchain/anthropic
2x cache double-count bug); the 5m/1h split comes from nested
``cache_creation.ephemeral_5m/1h_input_tokens``; reasoning is the count of
``thinking`` content blocks.

OpenAI: usage is in the FINAL chunk only and REQUIRES ``stream_options.include_usage``;
absent -> the stream is flagged ``partial_recovered`` rather than logging a silent zero.

A cancelled stream recovers whatever terminal value it has, else flags partial.
"""

from __future__ import annotations

from valuemaxx.capture.terminal import (
    AnthropicStreamAccumulator,
    OpenAIStreamAccumulator,
)

# --- Anthropic ---------------------------------------------------------------


def _anthropic_message_start(
    *,
    input_tokens: int,
    cache_read: int,
    cache_5m: int,
    cache_1h: int,
    output_tokens: int = 0,
) -> dict[str, object]:
    return {
        "type": "message_start",
        "message": {
            "usage": {
                "input_tokens": input_tokens,
                "cache_read_input_tokens": cache_read,
                "cache_creation_input_tokens": cache_5m + cache_1h,
                "cache_creation": {
                    "ephemeral_5m_input_tokens": cache_5m,
                    "ephemeral_1h_input_tokens": cache_1h,
                },
                "output_tokens": output_tokens,
            }
        },
    }


def _anthropic_message_delta(*, output_tokens: int) -> dict[str, object]:
    # message_delta.usage.output_tokens is the CUMULATIVE terminal value
    return {"type": "message_delta", "usage": {"output_tokens": output_tokens}}


def _thinking_block_start() -> dict[str, object]:
    return {"type": "content_block_start", "content_block": {"type": "thinking"}}


def test_anthropic_output_taken_terminally_not_summed() -> None:
    """test_anthropic_output_taken_terminally_not_summed: 60, not 35+60=95."""
    acc = AnthropicStreamAccumulator()
    acc.observe(_anthropic_message_start(input_tokens=100, cache_read=0, cache_5m=0, cache_1h=0))
    acc.observe(_anthropic_message_delta(output_tokens=35))  # intermediate cumulative
    acc.observe(_anthropic_message_delta(output_tokens=60))  # final cumulative (terminal)
    tokens = acc.finalize()
    assert tokens.output == 60  # the terminal value, NOT 35 + 60


def test_anthropic_cache_from_message_start_only_not_doubled() -> None:
    """test_anthropic_cache_from_message_start_only_not_doubled: the @langchain 2x bug fix."""
    acc = AnthropicStreamAccumulator()
    acc.observe(_anthropic_message_start(input_tokens=10, cache_read=200, cache_5m=50, cache_1h=30))
    # a (hypothetical) later event repeating cache fields must NOT be re-added
    acc.observe(_anthropic_message_delta(output_tokens=5))
    tokens = acc.finalize()
    assert tokens.cache_read == 200  # taken once, not doubled
    assert tokens.cache_write_5m == 50
    assert tokens.cache_write_1h == 30


def test_anthropic_5m_1h_split_from_nested_fields() -> None:
    """test_anthropic_5m_1h_split_from_nested_fields: 5m/1h come from nested cache_creation."""
    acc = AnthropicStreamAccumulator()
    acc.observe(_anthropic_message_start(input_tokens=10, cache_read=0, cache_5m=12, cache_1h=34))
    acc.observe(_anthropic_message_delta(output_tokens=1))
    tokens = acc.finalize()
    assert tokens.cache_write_5m == 12
    assert tokens.cache_write_1h == 34


def test_anthropic_reasoning_is_thinking_block_count() -> None:
    """test_anthropic_reasoning_is_thinking_block_count: reasoning derived from thinking blocks."""
    acc = AnthropicStreamAccumulator()
    acc.observe(_anthropic_message_start(input_tokens=10, cache_read=0, cache_5m=0, cache_1h=0))
    acc.observe(_thinking_block_start())
    acc.observe(_thinking_block_start())
    acc.observe(_anthropic_message_delta(output_tokens=50))
    tokens = acc.finalize()
    assert tokens.reasoning == 2  # two thinking blocks
    assert tokens.output >= tokens.reasoning  # reasoning embedded within output


def test_anthropic_is_streaming_true() -> None:
    acc = AnthropicStreamAccumulator()
    acc.observe(_anthropic_message_start(input_tokens=10, cache_read=0, cache_5m=0, cache_1h=0))
    acc.observe(_anthropic_message_delta(output_tokens=5))
    obs = acc.finalize_observation(provider="anthropic", model="claude-opus-4-8")
    assert obs.is_streaming is True
    assert obs.partial_recovered is False


def test_anthropic_cancelled_stream_recovers_partial_then_flags() -> None:
    """test_anthropic_cancelled_stream_recovers_partial_then_flags: partial, never silent zero."""
    acc = AnthropicStreamAccumulator()
    acc.observe(_anthropic_message_start(input_tokens=100, cache_read=0, cache_5m=0, cache_1h=0))
    acc.observe(_anthropic_message_delta(output_tokens=20))
    acc.mark_cancelled()  # stream cut off before message_stop
    obs = acc.finalize_observation(provider="anthropic", model="claude-opus-4-8")
    assert obs.partial_recovered is True  # flagged, never silently zero
    assert obs.tokens.output == 20  # we recovered the partial terminal value


# --- OpenAI ------------------------------------------------------------------


def _openai_usage_chunk(*, prompt: int, cached: int, completion: int) -> dict[str, object]:
    # OpenAI sends usage only in the FINAL chunk, and only with include_usage
    return {
        "usage": {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "prompt_tokens_details": {"cached_tokens": cached},
        }
    }


def _openai_content_chunk() -> dict[str, object]:
    return {"choices": [{"delta": {"content": "hi"}}], "usage": None}


def test_openai_usage_from_final_chunk() -> None:
    """test_openai_usage_from_final_chunk: usage taken from the final chunk only."""
    acc = OpenAIStreamAccumulator(include_usage=True)
    acc.observe(_openai_content_chunk())
    acc.observe(_openai_content_chunk())
    acc.observe(_openai_usage_chunk(prompt=100, cached=40, completion=25))
    tokens = acc.finalize()
    assert tokens.input_uncached == 60  # 100 prompt - 40 cached
    assert tokens.cache_read == 40
    assert tokens.output == 25


def test_openai_requires_include_usage_else_flags_partial() -> None:
    """test_openai_requires_include_usage_else_flags_partial: no usage -> partial, not zero."""
    acc = OpenAIStreamAccumulator(include_usage=False)
    acc.observe(_openai_content_chunk())
    acc.observe(_openai_content_chunk())  # no usage chunk ever arrives
    obs = acc.finalize_observation(provider="openai", model="gpt-5")
    assert obs.partial_recovered is True  # flagged loudly, never a silent zero
    assert obs.is_streaming is True


def test_openai_cancelled_without_usage_flags_partial() -> None:
    """test_openai_cancelled_without_usage_flags_partial: cancelled mid-stream -> partial."""
    acc = OpenAIStreamAccumulator(include_usage=True)
    acc.observe(_openai_content_chunk())
    acc.mark_cancelled()  # cut off before the final usage chunk
    obs = acc.finalize_observation(provider="openai", model="gpt-5")
    assert obs.partial_recovered is True
