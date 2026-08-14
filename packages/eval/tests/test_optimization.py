"""The optimization verdict — cost PER OUTCOME, not cost per token.

The eval funnel could already say "holds parity, 92% cheaper per token". That is the
commoditized half: it is a statement about spend, and every observability tool makes
it. The sentence this product exists to produce is different — *your cost per meeting
booked goes from $19.53 to $7.40, and the outcome rate did not measurably drop* — and
producing it requires joining three things that lived in separate places: the savings
estimate, the outcome denominator, and a verdict about whether the outcome rate held.

These tests pin the joins that make that sentence honest, and the refusals that keep
it from being fabricated when the evidence is thin.
"""

from __future__ import annotations

from decimal import Decimal

from valuemaxx.core.enums import CausalEvidence
from valuemaxx.eval.optimization import OptimizationVerdict, evaluate_switch


def _verdict(
    *,
    incumbent_usd: str = "82400",
    candidate_usd: str = "31200",
    incumbent_outcomes: int = 4218,
    candidate_successes: int | None = None,
    candidate_n: int | None = None,
    incumbent_successes: int | None = None,
    incumbent_n: int | None = None,
    margin: float = 0.01,
) -> OptimizationVerdict:
    return evaluate_switch(
        incumbent_usd=Decimal(incumbent_usd),
        candidate_usd=Decimal(candidate_usd),
        incumbent_outcomes=incumbent_outcomes,
        candidate_successes=candidate_successes,
        candidate_n=candidate_n,
        incumbent_successes=incumbent_successes,
        incumbent_n=incumbent_n,
        margin=margin,
    )


def test_the_headline_is_cost_per_outcome_on_both_sides() -> None:
    """Spend alone is not the product. Per-OUTCOME on both sides is."""
    v = _verdict()

    # $82,400 / 4,218 = 19.535… -> 19.54, and 31,200 / 4,218 = 7.3968… -> 7.40.
    # The plan's illustrative "$19.53" was a loose rounding of the same figures.
    assert v.incumbent_cost_per_outcome == Decimal("19.54")
    assert v.candidate_cost_per_outcome == Decimal("7.40")
    assert v.pct_change is not None
    assert v.pct_change < -60


def test_without_an_experiment_the_evidence_is_attributed_not_verified() -> None:
    """A saving with no experiment behind it must never claim causal proof.

    This is the axis the whole honesty model rests on. Repricing observed tokens
    proves what the SAME traffic would have cost; it proves nothing about whether
    the cheaper model would have produced the same outcomes. Labelling that
    `experimentally_verified` would be the single most damaging lie the product
    could tell, because it is the label a buyer acts on.
    """
    v = _verdict()

    assert v.causal_evidence is CausalEvidence.OBSERVATIONAL
    assert v.outcome_verdict is None
    assert v.safe_to_switch is False


def test_a_powered_experiment_earns_the_verified_label() -> None:
    """Real arms, enough units, rate held within the margin -> randomized evidence."""
    v = _verdict(
        candidate_successes=1_000,
        candidate_n=12_400,
        incumbent_successes=1_020,
        incumbent_n=12_400,
    )

    assert v.outcome_verdict is not None
    assert v.outcome_verdict.decided is True
    assert v.outcome_verdict.non_inferior is True
    assert v.causal_evidence is CausalEvidence.RANDOMIZED
    assert v.safe_to_switch is True


def test_an_underpowered_experiment_does_not_earn_it() -> None:
    """200 units per arm cannot decide a 1-point margin, so it stays observational.

    The dangerous shape: a real experiment was run, so the machinery is all present
    and it is tempting to report its verdict. But an undecided test is not evidence,
    and upgrading the label because an experiment merely EXISTED would let anyone
    buy `randomized` for the price of a small sample.
    """
    v = _verdict(
        candidate_successes=16,
        candidate_n=200,
        incumbent_successes=17,
        incumbent_n=200,
    )

    assert v.outcome_verdict is not None
    assert v.outcome_verdict.decided is False
    assert v.causal_evidence is CausalEvidence.OBSERVATIONAL
    assert v.safe_to_switch is False


def test_a_cheaper_model_that_loses_outcomes_is_not_safe_to_switch() -> None:
    """The case the loop exists to catch: cheaper per unit, worse per outcome.

    A model that halves spend while dropping the outcome rate by three points is
    not a saving — it is a revenue cut wearing a cost-reduction costume. Cost per
    outcome catches this where cost per token cannot.
    """
    v = _verdict(
        candidate_successes=640,
        candidate_n=12_400,
        incumbent_successes=1_020,
        incumbent_n=12_400,
    )

    assert v.outcome_verdict is not None
    assert v.outcome_verdict.non_inferior is False
    assert v.safe_to_switch is False


def test_zero_outcomes_yields_no_ratio_rather_than_a_divide_by_zero() -> None:
    """No denominator means no unit cost — never a fabricated one, never a crash."""
    v = _verdict(incumbent_outcomes=0)

    assert v.incumbent_cost_per_outcome is None
    assert v.candidate_cost_per_outcome is None
    assert v.safe_to_switch is False


def test_the_required_sample_size_is_reported_when_the_test_is_undecided() -> None:
    """Telling a user WHY it is undecided is the actionable half.

    "Insufficient data" without a target is a dead end; "you have 200 per arm and
    need 9,308" is a decision they can make — run longer, widen the margin, or
    accept the observational number.
    """
    v = _verdict(
        candidate_successes=16,
        candidate_n=200,
        incumbent_successes=17,
        incumbent_n=200,
    )

    assert v.required_n_per_arm is not None
    assert v.required_n_per_arm > 200
