"""Real captured cases for the eval funnel — replacing the fabricated default set.

``EvalService.run_eval_funnel`` graded a hardcoded 20-case list of ``("resolved",
"resolved")`` strings, so a recommendation said nothing about the host's actual
workload: the same verdict came back whatever their agents did. This turns recorded
runs into graded cases.

THE HONESTY PROBLEM THIS ALSO FIXES. The funnel used to hardcode
``has_outcome_labels=True``, ``has_human_labels=True``, ``judge_validated=True`` and
``human_verdict=True``. Those flags are exactly what selects the evidence rung
(``grade.py``), and the rung caps the grade — so asserting them made every run claim
``reliable`` regardless of what ground truth existed. :func:`build_case_set` DERIVES
them instead: outcome labels are claimed only when bound outcomes are actually present,
and human labels are never claimed, because nobody has reviewed anything. A run over
unlabeled traffic is now honestly ``directional``.

WHAT A CASE NEEDS, AND WHY SOME HOSTS HAVE NONE. A case is
``(case_id, incumbent_output, candidate_output)`` — it needs the text both models
produced. valuemaxx does not capture prompt/response content unless the host opts in
(``captureContent``), which is the right default and means a content-free deployment
has no comparable cases. :func:`build_case_set` reports that as an empty set with a
reason rather than silently falling back to fabricated data, because a confident
recommendation computed from invented cases is worse than no recommendation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import Sequence

    from valuemaxx.core.outcome import OutcomeEvent

# An eval spends real tokens per case, so a run is bounded by default. A larger sample
# tightens the parity estimate; it also multiplies the bill, and the operator approving
# the cost gate deserves a predictable number.
DEFAULT_MAX_CASES = 20


@dataclass(frozen=True, slots=True)
class CaseSet:
    """Graded-case inputs plus the ground truth that is actually available.

    ``cases`` is what the funnel grades. The three flags are what it may CLAIM about
    its evidence — derived here, never assumed, because they decide whether the
    resulting recommendation is allowed to read as ``reliable``.
    """

    cases: tuple[tuple[str, str, str], ...]
    has_outcome_labels: bool
    has_human_labels: bool
    """Why the set is empty (or short) — surfaced to the operator, never swallowed."""
    reason: str | None = None

    @property
    def is_empty(self) -> bool:
        """True when there is nothing real to grade."""
        return len(self.cases) == 0


def _text_from_raw(raw: object, key: str) -> str | None:
    """Pull a recorded text field out of an outcome's ``raw`` payload, if present."""
    if not isinstance(raw, dict):
        return None
    payload = cast("dict[str, object]", raw)
    value = payload.get(key)
    return value if isinstance(value, str) and value != "" else None


def build_case_set(
    outcomes: Sequence[OutcomeEvent],
    *,
    max_cases: int = DEFAULT_MAX_CASES,
) -> CaseSet:
    """Build graded cases from recorded outcomes, deriving the available ground truth.

    Only outcomes BOUND to a run are usable: an unbound outcome cannot be attributed to
    the work that produced it, so grading against it would compare a candidate to
    something the incumbent may never have done.

    A case needs the incumbent's recorded output and the candidate's output for the
    same input. Both live in the outcome's ``raw`` payload when the host opted into
    content capture; absent that, we return an empty set WITH a reason instead of
    inventing cases.
    """
    bound = [o for o in outcomes if o.binding.run_id is not None]
    if not bound:
        return CaseSet(
            cases=(),
            has_outcome_labels=False,
            has_human_labels=False,
            reason=(
                "no outcomes are bound to a run yet — record outcomes inside a `run(...)` "
                "scope so a candidate can be compared against what actually happened"
            ),
        )

    cases: list[tuple[str, str, str]] = []
    for outcome in bound[:max_cases]:
        incumbent = _text_from_raw(outcome.raw, "incumbent_output")
        candidate = _text_from_raw(outcome.raw, "candidate_output")
        if incumbent is None or candidate is None:
            continue
        cases.append((outcome.id, incumbent, candidate))

    if not cases:
        return CaseSet(
            cases=(),
            has_outcome_labels=True,
            has_human_labels=False,
            reason=(
                f"{len(bound)} bound outcome(s) found, but none carry comparable model "
                "output — enable content capture (`captureContent`) so the funnel has "
                "text to grade instead of fabricated cases"
            ),
        )

    return CaseSet(
        cases=tuple(cases),
        # Bound outcomes ARE the outcome labels — this is the one rung we can honestly
        # claim from captured data alone.
        has_outcome_labels=True,
        # Never claimed: no human has reviewed these. Asserting it would promote the
        # recommendation to `reliable` on evidence nobody produced.
        has_human_labels=False,
        reason=None if len(cases) >= len(bound[:max_cases]) else "some outcomes lacked output text",
    )


__all__ = ["DEFAULT_MAX_CASES", "CaseSet", "build_case_set"]
