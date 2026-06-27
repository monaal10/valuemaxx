"""smoke_no_ci_confirm_requires_ci — smoke drops >25% w/o CI; confirm needs CI (green; EVAL).

Successive halving (§8.4 M4): the **smoke** stage (n=30-50) eliminates candidates
underperforming the incumbent by >25% with **NO** confidence-interval requirement —
n is too small to separate CIs for small deltas. The **CI requirement applies only
to the final recommendation** on the confirmation set, where a winner needs its 95%
CI to separate from the incumbent's. ``valuemaxx.eval.search`` encodes exactly this:
``smoke_eval`` has no CI parameter; ``pick_winner`` requires ``ci_separated``.

``flags_violation`` flags a smoke stage that applies a CI requirement
(``require_ci95=True``). The negative fixture is that violation; the foundation
subject is the real search source. ``smoke_drops_without_ci_confirm_requires_ci``
exercises both halves of the invariant at runtime.
"""

from __future__ import annotations

from tests.conformance.astutil import package_src
from tests.conformance.rulebase import Rule, RuleKind

_MARKERS: tuple[str, ...] = ("require_ci95=True",)


def _flags(subject: object) -> bool:
    assert isinstance(subject, str)
    return any(marker in subject for marker in _MARKERS)


def _negative_fixture() -> object:
    return "smoke_eliminate(model, require_ci95=True)\n"


def _foundation_subject() -> object:
    # the real search stage: smoke has no CI param; confirmation requires CI separation.
    return (package_src("eval") / "search.py").read_text()


def smoke_drops_without_ci_confirm_requires_ci() -> bool:
    """Smoke eliminates a >25% loser with no CI; confirmation requires CI separation.

    Returns True iff (a) the smoke stage drops a clear underperformer on tiny n with
    no CI, and (b) the confirmation stage refuses to crown a winner whose CI overlaps
    the incumbent's — both halves of the §8.4 invariant.
    """
    from valuemaxx.eval.search import CandidateScore, pick_winner, smoke_eval

    incumbent_smoke = CandidateScore(model="inc", passes=40, n=40, cost_usd=1.0, latency_ms_p50=1.0)
    loser = CandidateScore(model="loser", passes=20, n=40, cost_usd=1.0, latency_ms_p50=1.0)
    survivors = smoke_eval(incumbent=incumbent_smoke, candidates=[loser])
    smoke_drops_loser_no_ci = all(s.model != "loser" for s in survivors)

    # confirmation: a candidate whose CI overlaps the incumbent's does not win.
    incumbent_conf = CandidateScore(
        model="inc", passes=150, n=300, cost_usd=1.0, latency_ms_p50=1.0
    )
    noisy = CandidateScore(model="noisy", passes=153, n=300, cost_usd=1.0, latency_ms_p50=1.0)
    confirm_requires_ci = pick_winner(incumbent=incumbent_conf, confirmed=[noisy]) is None

    return smoke_drops_loser_no_ci and confirm_requires_ci


RULE = Rule(
    name="smoke_no_ci_confirm_requires_ci",
    kind=RuleKind.STATIC,
    green_now=True,
    owner_task="EVAL",
    flags_violation=_flags,
    negative_fixture=_negative_fixture,
    foundation_subject=_foundation_subject,
)
