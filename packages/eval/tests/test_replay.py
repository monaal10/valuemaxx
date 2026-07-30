"""Replay — the only construction under which an eval is about the host's workload.

Before replay a "case" was two pre-stored strings and the candidate model was never
invoked, so a recommendation compared text the host happened to record rather than what
the candidate would actually produce. These tests pin the properties that make replay
trustworthy AND affordable: it calls the candidate for real, it is bounded because every
case costs money, a failed candidate call is dropped rather than scored as agreement,
and it never claims evidence nobody produced.
"""

from __future__ import annotations

import pytest
from valuemaxx.eval.replay import (
    DEFAULT_REPLAY_CASES,
    ReplaySample,
    build_replay_case_set,
    parse_samples,
)


class FakeRunner:
    """A candidate that echoes a fixed answer, recording every prompt it was given."""

    def __init__(self, answer: str = "candidate says hi") -> None:
        self.answer = answer
        self.prompts: list[str] = []

    def complete(self, *, model: str, prompt: str) -> str:
        del model
        self.prompts.append(prompt)
        return self.answer


class FailingRunner:
    """A candidate whose every call errors (a wrong key, a bad model id, an outage)."""

    def complete(self, *, model: str, prompt: str) -> str:
        del model, prompt
        raise RuntimeError("provider refused the request")


def _sample(n: int) -> ReplaySample:
    return ReplaySample(
        record_id=f"replay:run-{n}",
        prompt=f"summarize document {n}",
        incumbent_output=f"summary {n}",
    )


def test_replay_actually_calls_the_candidate_with_the_captured_prompt() -> None:
    """The whole point: the candidate's REAL output, on the host's REAL prompt."""
    runner = FakeRunner()
    result = build_replay_case_set([_sample(1)], runner=runner, candidate_model="claude-haiku-4-5")
    assert runner.prompts == ["summarize document 1"]
    # case = (id, what the incumbent really answered, what the candidate really answered)
    assert result.cases == (("replay:run-1", "summary 1", "candidate says hi"),)


def test_replay_never_claims_outcome_or_human_labels() -> None:
    """Replay shows what each model said — not whether either was CORRECT.

    Nobody labelled these, so replay alone earns the judge rung, which caps at
    `directional`. Claiming otherwise would manufacture confidence.
    """
    result = build_replay_case_set([_sample(1)], runner=FakeRunner(), candidate_model="m")
    assert result.has_outcome_labels is False
    assert result.has_human_labels is False


def test_replay_is_bounded_because_every_case_spends_money() -> None:
    runner = FakeRunner()
    build_replay_case_set(
        [_sample(i) for i in range(DEFAULT_REPLAY_CASES + 20)],
        runner=runner,
        candidate_model="m",
    )
    assert len(runner.prompts) == DEFAULT_REPLAY_CASES


def test_a_failed_candidate_call_is_dropped_not_scored_as_agreement() -> None:
    """Scoring a failure as parity would make an unreliable model look cheap AND equal."""
    result = build_replay_case_set([_sample(1)], runner=FailingRunner(), candidate_model="m")
    assert result.is_empty
    assert result.reason is not None
    assert "failed" in result.reason


def test_partial_failure_keeps_good_cases_and_reports_the_drops() -> None:
    class FlakyRunner:
        def __init__(self) -> None:
            self.calls = 0

        def complete(self, *, model: str, prompt: str) -> str:
            del model, prompt
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("transient")
            return "ok"

    result = build_replay_case_set(
        [_sample(1), _sample(2)], runner=FlakyRunner(), candidate_model="m"
    )
    assert len(result.cases) == 1
    assert result.reason is not None
    assert "dropped" in result.reason


def test_no_captured_prompts_says_how_to_get_them() -> None:
    """Content capture is opt-in, so an empty corpus is the DEFAULT, not an error."""
    result = build_replay_case_set([], runner=FakeRunner(), candidate_model="m")
    assert result.is_empty
    assert result.reason is not None
    assert "captureContent" in result.reason


@pytest.mark.parametrize(
    "payload",
    [
        {"prompt": "p"},  # no response
        {"response": "r"},  # no prompt
        {"prompt": "", "response": "r"},  # empty prompt
        "not-a-dict",
    ],
)
def test_incomplete_records_are_skipped_silently(payload: object) -> None:
    """A record without both halves is the content-capture-off case, not a failure."""
    assert parse_samples([("id", payload)]) == ()


def test_parses_a_complete_record() -> None:
    samples = parse_samples([("replay:r1", {"prompt": "p", "response": "r"})])
    assert samples == (ReplaySample(record_id="replay:r1", prompt="p", incumbent_output="r"),)
