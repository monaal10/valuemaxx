"""SEARCH: prune to a few + successive halving — smoke (no CI) then confirm (95% CI) (§8.4)."""

from __future__ import annotations

import pytest
from valuemaxx.eval.search import (
    CandidateScore,
    ParetoPoint,
    confirmation_eval,
    pareto_frontier,
    pick_winner,
    smoke_eval,
)


def _score(
    model: str, *, passes: int, n: int, cost: float = 1.0, latency: float = 100.0
) -> CandidateScore:
    return CandidateScore(model=model, passes=passes, n=n, cost_usd=cost, latency_ms_p50=latency)


# ---------------------------------------------------------------- smoke_eval


def test_smoke_eliminates_below_25_percent_no_ci() -> None:
    """A candidate >25% below the incumbent is eliminated at smoke — NO CI requirement (§8.4)."""
    incumbent = _score("incumbent", passes=40, n=40)  # parity 1.0
    candidates = [
        _score("good", passes=38, n=40),  # 0.95 -> survives
        _score("bad", passes=20, n=40),  # 0.50 -> >25% below -> eliminated
    ]
    survivors = smoke_eval(incumbent=incumbent, candidates=candidates)
    names = {s.model for s in survivors}
    assert "good" in names
    assert "bad" not in names


def test_smoke_keeps_within_25_percent() -> None:
    """A candidate within 25% of the incumbent survives the smoke stage."""
    incumbent = _score("incumbent", passes=40, n=40)
    candidates = [_score("ok", passes=31, n=40)]  # 0.775, within 25%
    survivors = smoke_eval(incumbent=incumbent, candidates=candidates)
    assert {s.model for s in survivors} == {"ok"}


def test_smoke_at_exactly_25_percent_survives() -> None:
    """At exactly 25% below (strict <), the candidate is NOT eliminated."""
    incumbent = _score("incumbent", passes=40, n=40)  # 1.0
    candidates = [_score("edge", passes=30, n=40)]  # 0.75 == 1.0*(1-0.25)
    survivors = smoke_eval(incumbent=incumbent, candidates=candidates)
    assert {s.model for s in survivors} == {"edge"}


def test_smoke_caps_survivors_to_three() -> None:
    """Successive halving caps the smoke survivors at the top 3 (§8.4)."""
    incumbent = _score("incumbent", passes=40, n=40)
    candidates = [_score(f"c{i}", passes=40 - i, n=40) for i in range(6)]  # all survive
    survivors = smoke_eval(incumbent=incumbent, candidates=candidates)
    assert len(survivors) == 3
    # the three kept are the highest-parity ones
    assert {s.model for s in survivors} == {"c0", "c1", "c2"}


def test_smoke_rejects_out_of_range_n() -> None:
    """Smoke runs on 30-50 cases; an out-of-range n is rejected (closed contract)."""
    incumbent = _score("incumbent", passes=40, n=40)
    with pytest.raises(ValueError, match="smoke"):
        smoke_eval(incumbent=incumbent, candidates=[_score("c", passes=10, n=10)])


# ---------------------------------------------------------------- confirmation_eval


def test_confirmation_requires_200_to_500_cases() -> None:
    """The confirmation stage runs on 200-500 cases; fewer is rejected."""
    incumbent = _score("incumbent", passes=300, n=300)
    with pytest.raises(ValueError, match="confirmation"):
        confirmation_eval(incumbent=incumbent, survivors=[_score("c", passes=40, n=40)])


def test_confirmation_passes_through_valid_survivors() -> None:
    """A valid confirmation run returns the survivors' scores for the winner pick."""
    incumbent = _score("incumbent", passes=270, n=300)
    survivors = [_score("c1", passes=285, n=300), _score("c2", passes=260, n=300)]
    confirmed = confirmation_eval(incumbent=incumbent, survivors=survivors)
    assert {c.model for c in confirmed} == {"c1", "c2"}


# ---------------------------------------------------------------- pick_winner


def test_winner_when_ci_separates_above_incumbent() -> None:
    """A candidate wins iff parity >= incumbent AND its 95% CI separates from the incumbent's."""
    incumbent = _score("incumbent", passes=150, n=300)  # ~0.50
    survivors = [_score("clear", passes=285, n=300)]  # ~0.95, CI well above
    winner = pick_winner(incumbent=incumbent, confirmed=survivors)
    assert winner is not None
    assert winner.model == "clear"


def test_no_winner_when_cis_overlap() -> None:
    """When no candidate's CI separates from the incumbent, there is no winner (None)."""
    incumbent = _score("incumbent", passes=150, n=300)  # 0.50
    survivors = [_score("noisy", passes=153, n=300)]  # 0.51, CIs overlap
    assert pick_winner(incumbent=incumbent, confirmed=survivors) is None


def test_winner_is_lowest_cost_among_separated() -> None:
    """Among candidates whose CIs separate above the incumbent, the lowest-cost wins (§8.4)."""
    incumbent = _score("incumbent", passes=150, n=300)
    survivors = [
        _score("pricey", passes=285, n=300, cost=10.0),
        _score("cheap", passes=284, n=300, cost=2.0),  # also separates, cheaper
    ]
    winner = pick_winner(incumbent=incumbent, confirmed=survivors)
    assert winner is not None
    assert winner.model == "cheap"


def test_no_winner_when_candidate_below_incumbent() -> None:
    """A candidate that is below the incumbent never wins, even if its CI separates."""
    incumbent = _score("incumbent", passes=285, n=300)  # 0.95
    survivors = [_score("worse", passes=150, n=300)]  # 0.50, separated but BELOW
    assert pick_winner(incumbent=incumbent, confirmed=survivors) is None


def test_pick_winner_empty_is_none() -> None:
    """No confirmed candidates -> no winner."""
    incumbent = _score("incumbent", passes=150, n=300)
    assert pick_winner(incumbent=incumbent, confirmed=[]) is None


# ---------------------------------------------------------------- pareto_frontier


def test_pareto_frontier_drops_dominated_points() -> None:
    """A point dominated on all of cost/quality/latency is flagged dominated (§8.4)."""
    points = [
        CandidateScore(model="a", passes=90, n=100, cost_usd=1.0, latency_ms_p50=100.0),
        # b is worse on every axis than a -> dominated
        CandidateScore(model="b", passes=80, n=100, cost_usd=2.0, latency_ms_p50=200.0),
    ]
    frontier = pareto_frontier(points)
    by_model = {p.model: p for p in frontier}
    assert by_model["a"].dominated is False
    assert by_model["b"].dominated is True


def test_pareto_frontier_keeps_tradeoffs() -> None:
    """Two points that each win on some axis are both on the frontier (neither dominated)."""
    points = [
        CandidateScore(model="hi_q", passes=95, n=100, cost_usd=5.0, latency_ms_p50=300.0),
        CandidateScore(model="cheap", passes=85, n=100, cost_usd=1.0, latency_ms_p50=80.0),
    ]
    frontier = pareto_frontier(points)
    assert all(p.dominated is False for p in frontier)


def test_pareto_point_carries_axes() -> None:
    """Each Pareto point exposes its quality/cost/latency for the report."""
    points = [CandidateScore(model="a", passes=90, n=100, cost_usd=1.0, latency_ms_p50=100.0)]
    point: ParetoPoint = pareto_frontier(points)[0]
    assert point.quality == pytest.approx(0.90)
    assert point.cost_usd == 1.0
    assert point.latency_ms_p50 == 100.0


def test_oss_costed_fully_loaded() -> None:
    """An OSS candidate is costed fully-loaded (GPU+ops / volume), not 'free per token' (§8.4)."""
    from valuemaxx.eval.search import fully_loaded_oss_cost

    # 1000 monthly calls, $720/mo fully-loaded infra -> $0.72 per call, never $0.
    per_call = fully_loaded_oss_cost(monthly_infra_usd=720.0, monthly_calls=1000)
    assert per_call == pytest.approx(0.72)


def test_oss_zero_volume_is_not_free() -> None:
    """At zero volume the fully-loaded per-call cost is the whole infra bill, not zero."""
    from valuemaxx.eval.search import fully_loaded_oss_cost

    per_call = fully_loaded_oss_cost(monthly_infra_usd=720.0, monthly_calls=0)
    assert per_call == pytest.approx(720.0)
