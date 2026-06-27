"""COSTGATE: BYO-keys two-phase gate — exact tokens, money half-even, keys never leak (§8.5)."""

from __future__ import annotations

import logging
from decimal import Decimal

import pytest
from valuemaxx.core import CostGatePhase, ProviderKeyRef
from valuemaxx.eval.costgate import (
    Phase1Approval,
    Phase2Approval,
    estimate_full_run_cost,
    estimate_smoke_cost,
    make_phase1_approval,
    make_phase2_approval,
    resolve_provider_key,
)
from valuemaxx.eval.errors import BudgetExceededError, GateNotApprovedError

# The runtime sentinel the no_secret_logging conformance rule looks for.
SENTINEL_KEY = "SENTINEL_KEY_8f3a"  # a test sentinel, not a real secret


class _CountingProvider:
    """A deterministic provider tokenizer: input = word count, output sampled per call.

    Deliberately NOT tiktoken — the count comes from the provider's own tokenizer
    (free count_tokens for Claude). Output sampling returns a fixed token count so
    the 5% extrapolation is exact under test.
    """

    def __init__(self, *, output_tokens_per_case: int = 50) -> None:
        self.sampled_calls = 0
        self._output_tokens = output_tokens_per_case

    def count_input_tokens(self, *, model: str, text: str) -> int:
        return len(text.split())

    def sample_output_tokens(self, *, model: str, text: str) -> int:
        self.sampled_calls += 1
        return self._output_tokens


def _cases(n: int) -> list[str]:
    # each case is 10 words -> 10 input tokens via the stub
    return [" ".join(["word"] * 10) for _ in range(n)]


# ---------------------------------------------------------------- estimate_smoke_cost


def test_smoke_cost_uses_exact_input_tokens() -> None:
    """Input tokens are counted exactly per case via the provider tokenizer (§8.5)."""
    provider = _CountingProvider(output_tokens_per_case=0)
    estimate = estimate_smoke_cost(
        provider=provider,
        model="claude-cheap",
        cases=_cases(40),
        input_price_per_1k=Decimal("0.001"),
        output_price_per_1k=Decimal("0.002"),
    )
    # 40 cases * 10 input tokens = 400 input tokens; output 0.
    # 400/1000 * 0.001 = 0.0004 -> rounds to 0.00 at 2dp half-even.
    assert estimate.phase is CostGatePhase.SMOKE
    assert estimate.n_cases == 40
    assert estimate.estimated_usd == Decimal("0.00")


def test_smoke_cost_samples_output_at_5_percent() -> None:
    """Output tokens are estimated sample-first: run ~5% of cases, extrapolate (§8.5)."""
    provider = _CountingProvider(output_tokens_per_case=100)
    estimate_smoke_cost(
        provider=provider,
        model="m",
        cases=_cases(40),
        input_price_per_1k=Decimal("0.001"),
        output_price_per_1k=Decimal("0.002"),
        sample_fraction=0.05,
    )
    # 5% of 40 = 2 sampled output calls (ceil to at least 1).
    assert provider.sampled_calls == 2


def test_smoke_cost_extrapolates_output_from_sample() -> None:
    """The sampled output rate is extrapolated to the full case count."""
    provider = _CountingProvider(output_tokens_per_case=100)
    estimate = estimate_smoke_cost(
        provider=provider,
        model="m",
        cases=_cases(40),
        input_price_per_1k=Decimal("0.000"),  # isolate output cost
        output_price_per_1k=Decimal("1.000"),
    )
    # sampled avg 100 output tokens/case -> 40*100 = 4000 output tokens.
    # 4000/1000 * 1.000 = 4.00
    assert estimate.estimated_usd == Decimal("4.00")


def test_smoke_cost_money_rounds_half_even() -> None:
    """Money is quantized to cents with ROUND_HALF_EVEN (banker's rounding)."""
    provider = _CountingProvider(output_tokens_per_case=0)
    # craft input tokens so the raw cost is exactly 0.005 -> half-even rounds to 0.00
    estimate = estimate_smoke_cost(
        provider=provider,
        model="m",
        cases=[" ".join(["w"] * 5)],  # 5 input tokens
        input_price_per_1k=Decimal("1.000"),  # 5/1000*1 = 0.005
        output_price_per_1k=Decimal("0.000"),
    )
    assert estimate.estimated_usd == Decimal("0.00")  # 0.005 -> 0.00 (round half to even)


def test_smoke_cost_never_uses_tiktoken_import() -> None:
    """AST guard: the costgate module never imports tiktoken (§5.2, no_tiktoken_for_cost)."""
    import ast
    from pathlib import Path

    src = Path(estimate_smoke_cost.__code__.co_filename).read_text(encoding="utf-8")
    tree = ast.parse(src)
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    assert "tiktoken" not in roots


# ---------------------------------------------------------------- make_phase1_approval


def test_phase1_refuses_over_budget() -> None:
    """Phase 1 refuses to start when the estimate exceeds the budget (§8.5 hard cap)."""
    provider = _CountingProvider(output_tokens_per_case=1000)
    estimate = estimate_smoke_cost(
        provider=provider,
        model="m",
        cases=_cases(40),
        input_price_per_1k=Decimal("0.000"),
        output_price_per_1k=Decimal("1.000"),
    )  # 40*1000/1000 * 1 = 40.00
    with pytest.raises(BudgetExceededError, match="budget"):
        make_phase1_approval(estimate=estimate, budget_usd=Decimal("10.00"))


def test_phase1_auto_approves_under_ceiling() -> None:
    """Under the auto-approve ceiling, phase 1 is approved without manual sign-off."""
    provider = _CountingProvider(output_tokens_per_case=0)
    estimate = estimate_smoke_cost(
        provider=provider,
        model="m",
        cases=_cases(40),
        input_price_per_1k=Decimal("0.001"),
        output_price_per_1k=Decimal("0.000"),
    )  # 0.00
    approval = make_phase1_approval(
        estimate=estimate, budget_usd=Decimal("10.00"), auto_approve_ceiling_usd=Decimal("1.00")
    )
    assert approval.approved is True
    assert approval.auto_approved is True


def test_phase1_requires_manual_above_ceiling() -> None:
    """Above the ceiling but within budget, phase 1 needs explicit manual approval."""
    provider = _CountingProvider(output_tokens_per_case=500)
    estimate = estimate_smoke_cost(
        provider=provider,
        model="m",
        cases=_cases(40),
        input_price_per_1k=Decimal("0.000"),
        output_price_per_1k=Decimal("1.000"),
    )  # 20.00
    # not auto-approved (above ceiling); manual approval must be supplied
    auto = make_phase1_approval(
        estimate=estimate, budget_usd=Decimal("100.00"), auto_approve_ceiling_usd=Decimal("1.00")
    )
    assert auto.approved is False
    assert auto.auto_approved is False
    manual = make_phase1_approval(
        estimate=estimate,
        budget_usd=Decimal("100.00"),
        auto_approve_ceiling_usd=Decimal("1.00"),
        manual_approved=True,
    )
    assert manual.approved is True
    assert manual.auto_approved is False


# ---------------------------------------------------------------- phase 2 ordering


def _approved_phase1() -> Phase1Approval:
    provider = _CountingProvider(output_tokens_per_case=0)
    estimate = estimate_smoke_cost(
        provider=provider,
        model="m",
        cases=_cases(40),
        input_price_per_1k=Decimal("0.001"),
        output_price_per_1k=Decimal("0.000"),
    )
    return make_phase1_approval(
        estimate=estimate, budget_usd=Decimal("10.00"), auto_approve_ceiling_usd=Decimal("1.00")
    )


def test_phase2_requires_phase1_approved() -> None:
    """Phase 2 cannot be estimated before phase 1 is approved (two_phase_gate_ordered)."""
    provider = _CountingProvider(output_tokens_per_case=50)
    unapproved = Phase1Approval(
        estimate=_approved_phase1().estimate, approved=False, auto_approved=False
    )
    with pytest.raises(GateNotApprovedError, match="phase 1"):
        estimate_full_run_cost(
            phase1=unapproved,
            provider=provider,
            model="m",
            cases=_cases(300),
            input_price_per_1k=Decimal("0.001"),
            output_price_per_1k=Decimal("0.002"),
        )


def test_phase2_estimate_after_phase1_approved() -> None:
    """With phase 1 approved, phase 2 estimates the projected full-run cost."""
    provider = _CountingProvider(output_tokens_per_case=50)
    estimate = estimate_full_run_cost(
        phase1=_approved_phase1(),
        provider=provider,
        model="m",
        cases=_cases(300),
        input_price_per_1k=Decimal("0.000"),
        output_price_per_1k=Decimal("1.000"),
    )
    assert estimate.phase is CostGatePhase.CONFIRMATION
    assert estimate.n_cases == 300
    # 300 * 50 output tokens = 15000; 15000/1000 * 1 = 15.00
    assert estimate.estimated_usd == Decimal("15.00")


def test_phase2_uses_measured_smoke_output_rate() -> None:
    """Phase 2 reuses the smoke-measured output rate rather than re-sampling blindly (§8.5)."""
    provider = _CountingProvider(output_tokens_per_case=50)
    # the provider's sample call count is the observable proxy: phase2 may re-sample,
    # but it must produce a finite, budget-checkable estimate from a measured rate.
    estimate = estimate_full_run_cost(
        phase1=_approved_phase1(),
        provider=provider,
        model="m",
        cases=_cases(300),
        input_price_per_1k=Decimal("0.000"),
        output_price_per_1k=Decimal("1.000"),
        measured_output_tokens_per_case=80,
    )
    # uses the measured rate (80), not a fresh sample: 300*80/1000*1 = 24.00
    assert estimate.estimated_usd == Decimal("24.00")


def test_phase2_approval_requires_phase1() -> None:
    """make_phase2_approval refuses if phase 1 was never approved."""
    provider = _CountingProvider(output_tokens_per_case=50)
    full = estimate_full_run_cost(
        phase1=_approved_phase1(),
        provider=provider,
        model="m",
        cases=_cases(300),
        input_price_per_1k=Decimal("0.000"),
        output_price_per_1k=Decimal("1.000"),
    )
    unapproved_phase1 = Phase1Approval(estimate=full, approved=False, auto_approved=False)
    with pytest.raises(GateNotApprovedError):
        make_phase2_approval(
            phase1=unapproved_phase1, full_run_estimate=full, budget_usd=Decimal("100.00")
        )


def test_phase2_approval_refuses_over_budget() -> None:
    """Phase 2 also refuses to start when the projected full-run exceeds budget."""
    provider = _CountingProvider(output_tokens_per_case=50)
    full = estimate_full_run_cost(
        phase1=_approved_phase1(),
        provider=provider,
        model="m",
        cases=_cases(300),
        input_price_per_1k=Decimal("0.000"),
        output_price_per_1k=Decimal("1.000"),
    )  # 15.00
    with pytest.raises(BudgetExceededError):
        make_phase2_approval(
            phase1=_approved_phase1(), full_run_estimate=full, budget_usd=Decimal("1.00")
        )


def test_phase2_approval_succeeds_within_budget() -> None:
    """A within-budget phase 2 is approved (the second sign-off)."""
    provider = _CountingProvider(output_tokens_per_case=50)
    full = estimate_full_run_cost(
        phase1=_approved_phase1(),
        provider=provider,
        model="m",
        cases=_cases(300),
        input_price_per_1k=Decimal("0.000"),
        output_price_per_1k=Decimal("1.000"),
    )
    approval: Phase2Approval = make_phase2_approval(
        phase1=_approved_phase1(), full_run_estimate=full, budget_usd=Decimal("100.00")
    )
    assert approval.approved is True


# ---------------------------------------------------------------- resolve_provider_key


def test_resolve_provider_key_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """A provider key is resolved from the env var named by the ref — never stored (§8.5)."""
    monkeypatch.setenv("VMX_TEST_PROVIDER_KEY", SENTINEL_KEY)
    ref = ProviderKeyRef(provider="anthropic", secret_ref="VMX_TEST_PROVIDER_KEY")
    key = resolve_provider_key(ref)
    assert key == SENTINEL_KEY


def test_resolve_provider_key_missing_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """A missing env var is a clear error, not a silent empty key."""
    monkeypatch.delenv("VMX_ABSENT_KEY", raising=False)
    ref = ProviderKeyRef(provider="anthropic", secret_ref="VMX_ABSENT_KEY")
    with pytest.raises(KeyError, match="VMX_ABSENT_KEY"):
        resolve_provider_key(ref)


def test_provider_key_never_on_any_model() -> None:
    """No costgate model field can hold a plaintext key (ProviderKeyRef has none)."""
    # ProviderKeyRef itself has only provider + secret_ref (no key/api_key field).
    fields = set(ProviderKeyRef.model_fields)
    assert fields == {"provider", "secret_ref"}
    for forbidden in ("key", "api_key", "secret_value", "plaintext"):
        assert forbidden not in fields


def test_resolved_key_never_logged(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Resolving + using a key emits no log line containing the sentinel (no_secret_logging)."""
    monkeypatch.setenv("VMX_TEST_PROVIDER_KEY", SENTINEL_KEY)
    ref = ProviderKeyRef(provider="anthropic", secret_ref="VMX_TEST_PROVIDER_KEY")
    with caplog.at_level(logging.DEBUG):
        key = resolve_provider_key(ref)
        # use the key the way the funnel would (build a header) and log around it
        _ = {"Authorization": f"Bearer {key}"}
        logging.getLogger("valuemaxx.eval").debug("resolved provider key for %s", ref.provider)
    dumped = caplog.text + "".join(str(r.args) for r in caplog.records)
    assert SENTINEL_KEY not in dumped


def test_cost_estimate_carries_no_key_field() -> None:
    """The CostEstimate the gate returns has no key-bearing field (keys never returned)."""
    provider = _CountingProvider(output_tokens_per_case=0)
    estimate = estimate_smoke_cost(
        provider=provider,
        model="m",
        cases=_cases(30),
        input_price_per_1k=Decimal("0.001"),
        output_price_per_1k=Decimal("0.001"),
    )
    for forbidden in ("key", "api_key", "secret_value", "secret_ref"):
        assert forbidden not in type(estimate).model_fields
