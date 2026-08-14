"""The optimization verdict: does switching improve cost PER OUTCOME, provably?

The eval funnel already answered two questions separately — "does the candidate hold
quality parity on replayed cases" (grade.py) and "what would the same traffic cost on
the candidate" (savings.py). Neither is the question a buyer asks. They ask whether
their cost per meeting booked goes down without the meetings going away, and answering
that means joining the spend estimate to the outcome denominator and to evidence about
whether the outcome rate actually held.

The join is easy. The discipline is the whole point:

* **Cost per outcome on BOTH sides.** A per-token saving is a statement about spend and
  says nothing about unit economics. A model that halves token cost while dropping the
  outcome rate by three points has raised the cost per outcome, and only this framing
  catches it.
* **A saving is not proof.** Repricing observed tokens proves what the same traffic
  would have cost. It proves nothing about whether the cheaper model would have
  produced the same outcomes, so an estimate alone stays OBSERVATIONAL and
  ``safe_to_switch`` stays false. Only a powered non-inferiority test upgrades it.
* **An experiment that ran is not an experiment that decided.** Upgrading the evidence
  label merely because arms exist would let anyone buy ``randomized`` for the price of
  a small sample. The verdict must be *decided* AND non-inferior.
* **Undecided reports what it would take.** "Insufficient data" alone is a dead end;
  "you have 200 per arm and need 9,308" is a decision the user can act on.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal

from valuemaxx.core.enums import CausalEvidence
from valuemaxx.eval.stats import (
    NonInferiorityVerdict,
    non_inferiority,
    required_sample_size,
)

_CENTS = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class OptimizationVerdict:
    """Whether a switch improves cost per outcome, and how much to trust that.

    ``safe_to_switch`` is deliberately conservative: it is true only when the unit
    cost falls AND a powered experiment says the outcome rate held. Everything else
    — a saving with no experiment, an underpowered one, a real regression — is false.
    A user may still choose to switch on observational evidence; the flag says whether
    the system can back that choice, not whether they are allowed to make it.
    """

    incumbent_cost_per_outcome: Decimal | None
    candidate_cost_per_outcome: Decimal | None
    pct_change: Decimal | None
    outcome_verdict: NonInferiorityVerdict | None
    causal_evidence: CausalEvidence
    safe_to_switch: bool
    required_n_per_arm: int | None


def evaluate_switch(
    *,
    incumbent_usd: Decimal,
    candidate_usd: Decimal,
    incumbent_outcomes: int,
    candidate_successes: int | None = None,
    candidate_n: int | None = None,
    incumbent_successes: int | None = None,
    incumbent_n: int | None = None,
    margin: float = 0.01,
) -> OptimizationVerdict:
    """Join a spend estimate to an outcome denominator and an optional experiment.

    ``incumbent_usd`` is what was actually spent; ``candidate_usd`` is that same
    traffic repriced (see ``savings.estimate_switch``). ``incumbent_outcomes`` is the
    billing-grade denominator over the same window — the number the cost is *per*.

    The four experiment arguments are all-or-nothing. Supplying them runs a
    non-inferiority test on the outcome rate; omitting them leaves the verdict
    observational, which is the honest state for a repricing with no experiment
    behind it.
    """
    per_incumbent = _ratio(incumbent_usd, incumbent_outcomes)
    per_candidate = _ratio(candidate_usd, incumbent_outcomes)
    pct = _pct_change(per_incumbent, per_candidate)

    verdict = _run_experiment(
        candidate_successes=candidate_successes,
        candidate_n=candidate_n,
        incumbent_successes=incumbent_successes,
        incumbent_n=incumbent_n,
        margin=margin,
    )

    proven = verdict is not None and verdict.decided and verdict.non_inferior is True
    evidence = CausalEvidence.RANDOMIZED if proven else CausalEvidence.OBSERVATIONAL
    cheaper = pct is not None and pct < 0

    return OptimizationVerdict(
        incumbent_cost_per_outcome=per_incumbent,
        candidate_cost_per_outcome=per_candidate,
        pct_change=pct,
        outcome_verdict=verdict,
        causal_evidence=evidence,
        safe_to_switch=proven and cheaper,
        required_n_per_arm=_required_n(verdict),
    )


def _run_experiment(
    *,
    candidate_successes: int | None,
    candidate_n: int | None,
    incumbent_successes: int | None,
    incumbent_n: int | None,
    margin: float,
) -> NonInferiorityVerdict | None:
    """The non-inferiority test, or None when no experiment was supplied.

    All four arms are required together: a partially-specified experiment is a
    caller bug, and inventing the missing half would manufacture a verdict.
    """
    if (
        candidate_successes is None
        or candidate_n is None
        or incumbent_successes is None
        or incumbent_n is None
    ):
        return None
    return non_inferiority(
        candidate_successes=candidate_successes,
        candidate_n=candidate_n,
        incumbent_successes=incumbent_successes,
        incumbent_n=incumbent_n,
        margin=margin,
    )


def _required_n(verdict: NonInferiorityVerdict | None) -> int | None:
    """How many units per arm an undecided test would need to decide.

    Only meaningful for an undecided verdict — a decided one already has what it
    needs, and reporting a target beside a conclusion invites the reader to think
    the conclusion is provisional.
    """
    if verdict is None or verdict.decided:
        return None
    return required_sample_size(baseline_rate=verdict.incumbent_rate, margin=verdict.margin)


def _ratio(usd: Decimal, outcomes: int) -> Decimal | None:
    """Cost per outcome, or None when there is no denominator.

    A zero denominator is "nothing has bound yet", which is a different fact from
    "this is free". Returning None keeps the caller from rendering the second.
    """
    if outcomes <= 0:
        return None
    return (usd / Decimal(outcomes)).quantize(_CENTS, rounding=ROUND_HALF_EVEN)


def _pct_change(incumbent: Decimal | None, candidate: Decimal | None) -> Decimal | None:
    """Percent change in unit cost; negative is a saving."""
    if incumbent is None or candidate is None or incumbent == 0:
        return None
    return ((candidate - incumbent) / incumbent * Decimal(100)).quantize(_CENTS)


__all__ = ["OptimizationVerdict", "evaluate_switch"]
