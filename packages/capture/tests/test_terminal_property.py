"""PG3 — property: Anthropic output is the LAST cumulative value for any delta sequence.

The terminal-value rule must hold for *any* sequence of message_delta usage values,
not just hand-picked ones: the accumulated output equals the final delta's
cumulative output_tokens — never the sum of the deltas (which is the 2x bug class).
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st
from valuemaxx.capture.terminal import AnthropicStreamAccumulator


@given(st.lists(st.integers(min_value=0, max_value=100_000), min_size=1, max_size=20))
def test_output_is_terminal_for_any_delta_sequence(cumulative_outputs: list[int]) -> None:
    """test_output_is_terminal_for_any_delta_sequence: output == last cumulative, never the sum."""
    acc = AnthropicStreamAccumulator()
    acc.observe(
        {
            "type": "message_start",
            "message": {
                "usage": {
                    "input_tokens": 10,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0,
                    "cache_creation": {
                        "ephemeral_5m_input_tokens": 0,
                        "ephemeral_1h_input_tokens": 0,
                    },
                    "output_tokens": 0,
                }
            },
        }
    )
    for cumulative in cumulative_outputs:
        acc.observe({"type": "message_delta", "usage": {"output_tokens": cumulative}})
    tokens = acc.finalize()
    assert tokens.output == cumulative_outputs[-1]  # terminal value
    # and crucially NOT the sum (unless the sequence is trivially one element)
    if len(cumulative_outputs) > 1 and sum(cumulative_outputs) != cumulative_outputs[-1]:
        assert tokens.output != sum(cumulative_outputs)
