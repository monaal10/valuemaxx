"""The production eval seams — driven through a fake HTTP post, so no tokens are spent.

Until these existed the funnel had only test stubs for its three protocols, so
``run_eval_funnel`` could not run anywhere. What matters here is not that an HTTP call
is made but that the honesty properties hold: the provider's OWN token counts are used
(never a local re-tokenization), a judge that cannot answer scores against parity
rather than crashing the run, and a score is clamped to [0, 1] so a confused grader
cannot manufacture super-parity.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from valuemaxx.eval.providers import (
    AnthropicEvalProvider,
    ProviderCallError,
    StructuralReconstructibilityValidator,
)
from valuemaxx.eval.types import TaskType

if TYPE_CHECKING:
    from collections.abc import Mapping


class FakePost:
    """An injected HTTP seam returning canned bodies; records what was sent."""

    def __init__(self, *responses: object) -> None:
        self._responses = list(responses)
        self.sent: list[Mapping[str, object]] = []

    def post(self, url: str, headers: Mapping[str, str], body: Mapping[str, object]) -> object:
        del url, headers
        self.sent.append(body)
        return self._responses.pop(0) if self._responses else {}


def _provider(*responses: object) -> tuple[AnthropicEvalProvider, FakePost]:
    http = FakePost(*responses)
    return AnthropicEvalProvider(http=http, api_key="test-key"), http


def test_count_input_tokens_uses_the_providers_own_counter() -> None:
    provider, http = _provider({"input_tokens": 1234})
    assert provider.count_input_tokens(model="claude-haiku-4-5", text="hello") == 1234
    # The free count_tokens endpoint, not a local tokenizer that would be wrong for
    # any model family it was not built for.
    assert http.sent[0]["model"] == "claude-haiku-4-5"


def test_sample_output_tokens_reads_the_usage_block() -> None:
    provider, _ = _provider({"content": [], "usage": {"output_tokens": 77}})
    assert provider.sample_output_tokens(model="claude-haiku-4-5", text="x") == 77


def test_missing_usage_is_an_error_not_a_zero() -> None:
    """A silent 0 would read as 'this candidate is free' — the worst possible default."""
    provider, _ = _provider({"content": []})
    with pytest.raises(ProviderCallError):
        provider.sample_output_tokens(model="claude-haiku-4-5", text="x")


def test_complete_extracts_the_assistant_text() -> None:
    provider, _ = _provider(
        {"content": [{"type": "text", "text": "hello "}, {"type": "text", "text": "world"}]}
    )
    assert provider.complete(model="claude-haiku-4-5", prompt="hi") == "hello world"


def test_grade_parses_a_bare_score() -> None:
    provider, http = _provider({"content": [{"type": "text", "text": "0.85"}]})
    score = provider.grade(prediction="a", reference="b", rubric="match?")
    assert score == pytest.approx(0.85)
    # Grading is not the product: the judge gets a tiny budget on a cheap model.
    assert http.sent[0]["max_tokens"] == 16


def test_grade_clamps_out_of_range_scores() -> None:
    """A grader claiming 1.7 must not manufacture better-than-parity evidence."""
    provider, _ = _provider({"content": [{"type": "text", "text": "1.7"}]})
    assert provider.grade(prediction="a", reference="b", rubric="r") == pytest.approx(1.0)


def test_unparseable_grade_scores_against_parity_rather_than_crashing() -> None:
    """A judge that cannot answer is evidence AGAINST a switch, not a failed run."""
    provider, _ = _provider({"content": [{"type": "text", "text": "I cannot say"}]})
    assert provider.grade(prediction="a", reference="b", rubric="r") == pytest.approx(0.0)


def test_structural_validator_follows_the_task_type_rule() -> None:
    validator = StructuralReconstructibilityValidator()
    # Only deterministic task families reconstruct their outcome from output alone.
    assert validator.is_outcome_reconstructible_from_output(TaskType.CLASSIFICATION) is True
    assert validator.is_outcome_reconstructible_from_output(TaskType.OPEN_ENDED) is False
