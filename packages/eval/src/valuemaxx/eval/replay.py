"""Replay — re-run a host's REAL captured prompts against a candidate model.

This is what makes an eval mean something. Before it, a "case" was a pair of
pre-stored strings and the candidate model was never invoked at all: a recommendation
compared text the host happened to record, not what the candidate would actually
produce. `AnthropicEvalProvider.complete()` existed and nothing called it.

Replay closes that. For each captured call we have the prompt and the incumbent's
recorded response; we send the SAME prompt to the candidate and grade its real output
against the incumbent's real output. That is the only construction under which
"would a cheaper model hold this outcome" is a question about the host's workload
rather than about fixtures.

Three properties this deliberately preserves:

* **It spends money, so it is bounded.** Every case is one live call to the candidate.
  `max_cases` caps the run and the operator approves an estimate before it happens —
  an unbounded replay over a busy tenant is a surprise invoice.
* **A failed candidate call is not a passing case.** If the candidate errors we drop
  the case and say so, rather than scoring it as agreement (which would make an
  unreliable model look cheap AND equivalent).
* **No content, no replay.** Prompts exist only when the host opted into content
  capture. Absent them we return an empty set with a reason — never a fabricated
  prompt, because a plausible-looking eval over invented inputs is worse than none.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, cast

from valuemaxx.eval.cases import CaseSet

if TYPE_CHECKING:
    from collections.abc import Sequence

_LOG = logging.getLogger(__name__)

# Replay is the expensive path: one live candidate call per case. Ten is enough to see
# a parity signal and small enough that an operator approving the gate is not surprised.
DEFAULT_REPLAY_CASES = 10


class CandidateRunner(Protocol):
    """Runs one prompt against the candidate model (the live half of replay)."""

    def complete(self, *, model: str, prompt: str) -> str:
        """Return the candidate's output for ``prompt``."""
        ...


@dataclass(frozen=True, slots=True)
class ReplaySample:
    """One captured call: the prompt and what the incumbent actually answered."""

    record_id: str
    prompt: str
    incumbent_output: str


def parse_samples(records: Sequence[tuple[str, object]]) -> tuple[ReplaySample, ...]:
    """Turn stored raw records into replay samples, skipping any without both fields.

    A record missing prompt or response is not an error — it is the content-capture-off
    default — so it is skipped silently rather than failing the run.
    """
    samples: list[ReplaySample] = []
    for record_id, payload in records:
        if not isinstance(payload, dict):
            continue
        typed = cast("dict[str, object]", payload)
        prompt = typed.get("prompt")
        response = typed.get("response")
        if not isinstance(prompt, str) or not isinstance(response, str):
            continue
        if prompt == "" or response == "":
            continue
        samples.append(ReplaySample(record_id=record_id, prompt=prompt, incumbent_output=response))
    return tuple(samples)


def build_replay_case_set(
    samples: Sequence[ReplaySample],
    *,
    runner: CandidateRunner,
    candidate_model: str,
    max_cases: int = DEFAULT_REPLAY_CASES,
) -> CaseSet:
    """Run each sample's prompt through the candidate and build graded cases.

    Returns cases of ``(record_id, incumbent_output, candidate_output)`` where the
    candidate output is a LIVE result, not stored text.

    Ground truth: replay produces a real side-by-side comparison, but nobody has
    labelled whether the candidate's answer was *correct* — so human labels are never
    claimed, and outcome labels are claimed only by the caller that knows its outcomes
    are bound. Replay alone earns the judge rung, which caps at `directional`. Calling
    it `reliable` would be exactly the over-claim this codebase keeps guarding against.
    """
    if not samples:
        return CaseSet(
            cases=(),
            has_outcome_labels=False,
            has_human_labels=False,
            reason=(
                "no captured prompts to replay — enable content capture "
                "(`captureContent`) so the funnel can re-run real prompts against a "
                "candidate instead of comparing stored strings"
            ),
        )

    cases: list[tuple[str, str, str]] = []
    failed = 0
    for sample in samples[:max_cases]:
        try:
            candidate_output = runner.complete(model=candidate_model, prompt=sample.prompt)
        except Exception:
            # Dropping is the honest move: scoring a failed call as agreement would make
            # an unreliable candidate look both cheaper AND equivalent.
            _LOG.warning(
                "valuemaxx eval: candidate %s failed on case %s; dropping the case",
                candidate_model,
                sample.record_id,
            )
            failed += 1
            continue
        cases.append((sample.record_id, sample.incumbent_output, candidate_output))

    if not cases:
        return CaseSet(
            cases=(),
            has_outcome_labels=False,
            has_human_labels=False,
            reason=f"every candidate call failed ({failed} attempted)",
        )

    return CaseSet(
        cases=tuple(cases),
        has_outcome_labels=False,
        has_human_labels=False,
        reason=(f"{failed} case(s) dropped: the candidate call failed" if failed else None),
    )


__all__ = [
    "DEFAULT_REPLAY_CASES",
    "CandidateRunner",
    "ReplaySample",
    "build_replay_case_set",
    "parse_samples",
]
