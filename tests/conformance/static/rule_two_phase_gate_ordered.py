"""two_phase_gate_ordered — phase-2 cost gate only after phase-1 approved (green; owner EVAL).

The BYO-keys cost gate is two-phase and **strictly ordered** (§8.5 M2): the
projected full-run (phase 2) is only estimable after the smoke cost (phase 1) is
approved. In ``valuemaxx.eval.costgate`` this is structural — ``estimate_full_run_cost``
and ``make_phase2_approval`` both refuse with :class:`GateNotApprovedError` unless
``phase1.approved`` — so no path runs the confirmation set without the smoke guard.

``flags_violation`` flags a source that runs the confirmation set with no smoke
guard. The negative fixture is that violation; the foundation subject is the real
costgate source, which guards every phase-2 entry. ``phase2_refused_before_phase1``
exercises the runtime ordering invariant.
"""

from __future__ import annotations

from tests.conformance.astutil import package_src
from tests.conformance.rulebase import Rule, RuleKind

_MARKERS: tuple[str, ...] = ("run_confirmation_set(",)


def _flags(subject: object) -> bool:
    assert isinstance(subject, str)
    return any(marker in subject for marker in _MARKERS)


def _negative_fixture() -> object:
    return "run_confirmation_set()  # no smoke_approved guard\n"


def _foundation_subject() -> object:
    # the real two-phase cost gate: phase 2 is guarded behind phase-1 approval.
    return (package_src("eval") / "costgate.py").read_text()


def phase2_refused_before_phase1() -> bool:
    """Phase-2 estimation raises GateNotApprovedError when phase 1 is not approved.

    Returns True iff an unapproved phase-1 makes ``estimate_full_run_cost`` refuse —
    the ordering invariant, executed.
    """
    from decimal import Decimal

    from valuemaxx.core import CostEstimate, CostGatePhase
    from valuemaxx.eval.costgate import Phase1Approval, estimate_full_run_cost
    from valuemaxx.eval.errors import GateNotApprovedError

    class _Provider:
        def count_input_tokens(self, *, model: str, text: str) -> int:
            return 1

        def sample_output_tokens(self, *, model: str, text: str) -> int:
            return 1

    unapproved = Phase1Approval(
        estimate=CostEstimate(
            phase=CostGatePhase.SMOKE,
            provider="anthropic",
            model="m",
            estimated_usd=Decimal("0.00"),
            n_cases=1,
        ),
        approved=False,
        auto_approved=False,
    )
    try:
        estimate_full_run_cost(
            phase1=unapproved,
            provider=_Provider(),
            model="m",
            cases=["x"],
            input_price_per_1k=Decimal("0.001"),
            output_price_per_1k=Decimal("0.002"),
        )
    except GateNotApprovedError:
        return True
    return False


RULE = Rule(
    name="two_phase_gate_ordered",
    kind=RuleKind.STATIC,
    green_now=True,
    owner_task="EVAL",
    flags_violation=_flags,
    negative_fixture=_negative_fixture,
    foundation_subject=_foundation_subject,
)
