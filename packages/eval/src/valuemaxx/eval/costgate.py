"""COSTGATE — the BYO-keys two-phase cost gate (§8.5; the estimate IS the consent).

True full-run cost is only knowable after smoke-eval reveals the survivors, so the
gate is **two-phase, strictly ordered**:

1. **Phase 1** gates the *smoke-eval* cost up front — input tokens counted **exactly**
   via the provider's own tokenizer (free ``count_tokens`` for Claude; **never
   tiktoken**, which undercounts Claude), output tokens estimated **sample-first**
   (run ~5%, measure, extrapolate). One approval (auto under a ceiling, manual above,
   refuse over budget).
2. **Phase 2** gates the *projected full-run* on the confirmation set — **and cannot
   be constructed before phase 1 is approved** (``two_phase_gate_ordered``). A second
   approval before the expensive stage.

Money is computed in :class:`~decimal.Decimal` and quantized to cents with
``ROUND_HALF_EVEN``. Provider keys are resolved from env/secret-manager **only for
the run's duration** — they are never put on any model, never logged, and never
returned by any read API (``no_secret_logging``; ``ProviderKeyRef`` has no plaintext
field).
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from valuemaxx.core import CostEstimate, CostGatePhase
from valuemaxx.eval.errors import BudgetExceededError, GateNotApprovedError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from valuemaxx.core import ProviderKeyRef

_CENTS = Decimal("0.01")
_DEFAULT_SAMPLE_FRACTION = 0.05


@runtime_checkable
class ProviderTokenizer(Protocol):
    """The injected provider tokenizer (the provider's own counter, NEVER tiktoken).

    ``count_input_tokens`` is the exact per-candidate input count (free
    ``count_tokens`` for Claude); ``sample_output_tokens`` runs one case to measure
    its output length for the sample-first extrapolation.
    """

    def count_input_tokens(self, *, model: str, text: str) -> int:
        """Count the input tokens for ``text`` under ``model`` (provider tokenizer)."""
        ...

    def sample_output_tokens(self, *, model: str, text: str) -> int:
        """Run ``text`` under ``model`` and return the measured output-token count."""
        ...


@dataclass(frozen=True, slots=True)
class Phase1Approval:
    """The phase-1 (smoke) gate decision — carries the estimate it gated.

    ``approved`` is the consent; ``auto_approved`` distinguishes an under-ceiling
    auto-approval from a manual sign-off. Phase 2 reads ``approved`` to enforce
    ordering.
    """

    estimate: CostEstimate
    approved: bool
    auto_approved: bool


@dataclass(frozen=True, slots=True)
class Phase2Approval:
    """The phase-2 (projected full-run) gate decision — only reachable after phase 1."""

    estimate: CostEstimate
    approved: bool


def estimate_smoke_cost(
    *,
    provider: ProviderTokenizer,
    model: str,
    cases: Sequence[str],
    input_price_per_1k: Decimal,
    output_price_per_1k: Decimal,
    sample_fraction: float = _DEFAULT_SAMPLE_FRACTION,
    provider_name: str = "",
) -> CostEstimate:
    """Estimate the smoke-eval cost: exact input tokens + sample-first output (§8.5).

    Input tokens are counted exactly for every case via the provider tokenizer.
    Output tokens are estimated by running ``sample_fraction`` of the cases (at least
    one), measuring their output length, and extrapolating the per-case average to
    the full set. The money is quantized to cents with ``ROUND_HALF_EVEN``.

    Returns:
        A core :class:`~valuemaxx.core.CostEstimate` with ``phase=SMOKE`` (no key
        field — keys are never returned).
    """
    return _estimate(
        provider=provider,
        model=model,
        cases=cases,
        input_price_per_1k=input_price_per_1k,
        output_price_per_1k=output_price_per_1k,
        sample_fraction=sample_fraction,
        phase=CostGatePhase.SMOKE,
        measured_output_tokens_per_case=None,
        provider_name=provider_name,
    )


def make_phase1_approval(
    *,
    estimate: CostEstimate,
    budget_usd: Decimal,
    auto_approve_ceiling_usd: Decimal = Decimal("0"),
    manual_approved: bool = False,
) -> Phase1Approval:
    """Decide the phase-1 gate: refuse over budget, auto under ceiling, else manual.

    Args:
        estimate: the smoke-cost estimate (the consent surface).
        budget_usd: the hard cap — the gate refuses to start if ``estimate > budget``.
        auto_approve_ceiling_usd: under this, the gate auto-approves.
        manual_approved: an explicit manual sign-off for above-ceiling estimates.

    Raises:
        BudgetExceededError: if the estimate exceeds ``budget_usd``.
    """
    if estimate.estimated_usd > budget_usd:
        raise BudgetExceededError(
            f"smoke estimate {estimate.estimated_usd} exceeds budget {budget_usd}; gate refuses"
        )
    auto = estimate.estimated_usd <= auto_approve_ceiling_usd
    approved = auto or manual_approved
    return Phase1Approval(estimate=estimate, approved=approved, auto_approved=auto)


def estimate_full_run_cost(
    *,
    phase1: Phase1Approval,
    provider: ProviderTokenizer,
    model: str,
    cases: Sequence[str],
    input_price_per_1k: Decimal,
    output_price_per_1k: Decimal,
    sample_fraction: float = _DEFAULT_SAMPLE_FRACTION,
    measured_output_tokens_per_case: int | None = None,
    provider_name: str = "",
) -> CostEstimate:
    """Estimate the projected full-run cost — ONLY after phase 1 is approved (§8.5 M2).

    This is the ``two_phase_gate_ordered`` invariant in code: phase 2 cannot be
    constructed until ``phase1.approved`` is True. When the smoke stage already
    measured the per-case output rate, pass it as ``measured_output_tokens_per_case``
    so phase 2 reuses the measured rate instead of re-sampling blindly.

    Raises:
        GateNotApprovedError: if ``phase1`` is not approved.
    """
    if not phase1.approved:
        raise GateNotApprovedError(
            "phase 1 (smoke) must be approved before the phase-2 full-run estimate "
            "(two_phase_gate_ordered)"
        )
    return _estimate(
        provider=provider,
        model=model,
        cases=cases,
        input_price_per_1k=input_price_per_1k,
        output_price_per_1k=output_price_per_1k,
        sample_fraction=sample_fraction,
        phase=CostGatePhase.CONFIRMATION,
        measured_output_tokens_per_case=measured_output_tokens_per_case,
        provider_name=provider_name,
    )


def make_phase2_approval(
    *,
    phase1: Phase1Approval,
    full_run_estimate: CostEstimate,
    budget_usd: Decimal,
    manual_approved: bool = True,
) -> Phase2Approval:
    """Decide the phase-2 gate — only after phase 1, refusing over budget (§8.5).

    Raises:
        GateNotApprovedError: if ``phase1`` is not approved.
        BudgetExceededError: if the projected full-run exceeds ``budget_usd``.
    """
    if not phase1.approved:
        raise GateNotApprovedError(
            "phase 1 must be approved before phase 2 (two_phase_gate_ordered)"
        )
    if full_run_estimate.estimated_usd > budget_usd:
        raise BudgetExceededError(
            f"projected full-run {full_run_estimate.estimated_usd} exceeds budget "
            f"{budget_usd}; gate refuses"
        )
    return Phase2Approval(estimate=full_run_estimate, approved=manual_approved)


def resolve_provider_key(ref: ProviderKeyRef) -> str:
    """Resolve a provider key from the env var / secret ref — never stored, never logged.

    The returned string is held by the caller only for the run's duration; it is
    never placed on a model, never logged, and never returned by any read API (§8.5,
    ``no_secret_logging``). A missing ref is a clear ``KeyError`` — never a silent
    empty key.

    Raises:
        KeyError: if the referenced env var is not set.
    """
    return os.environ[ref.secret_ref]


def _estimate(
    *,
    provider: ProviderTokenizer,
    model: str,
    cases: Sequence[str],
    input_price_per_1k: Decimal,
    output_price_per_1k: Decimal,
    sample_fraction: float,
    phase: CostGatePhase,
    measured_output_tokens_per_case: int | None,
    provider_name: str,
) -> CostEstimate:
    """Shared exact-input + sample-first-output cost computation for both phases."""
    n = len(cases)
    input_tokens = sum(provider.count_input_tokens(model=model, text=case) for case in cases)

    if measured_output_tokens_per_case is not None:
        output_tokens = measured_output_tokens_per_case * n
    elif n == 0:
        output_tokens = 0
    else:
        sample_size = max(1, math.ceil(n * sample_fraction))
        sampled = sum(
            provider.sample_output_tokens(model=model, text=cases[i]) for i in range(sample_size)
        )
        per_case = sampled / sample_size
        output_tokens = round(per_case * n)

    input_cost = (Decimal(input_tokens) / Decimal(1000)) * input_price_per_1k
    output_cost = (Decimal(output_tokens) / Decimal(1000)) * output_price_per_1k
    total = (input_cost + output_cost).quantize(_CENTS, rounding=ROUND_HALF_EVEN)
    return CostEstimate(
        phase=phase,
        provider=provider_name,  # the candidate's provider name; never the key
        model=model,
        estimated_usd=total,
        n_cases=n,
    )


__all__ = [
    "Phase1Approval",
    "Phase2Approval",
    "ProviderTokenizer",
    "estimate_full_run_cost",
    "estimate_smoke_cost",
    "make_phase1_approval",
    "make_phase2_approval",
    "resolve_provider_key",
]
