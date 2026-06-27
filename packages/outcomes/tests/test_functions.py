"""OUT-B: install_function_rules — wrapt patch of a named symbol, predicate-gated emit."""

from __future__ import annotations

import sys
import types
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from valuemaxx.core import RunId, SignalClass, TenantId, active_run_id
from valuemaxx.outcomes.instrument.emitter import OutcomeEmitter
from valuemaxx.outcomes.instrument.functions import install_function_rules
from valuemaxx.outcomes.repository import InMemoryOutcomeEventRepository
from valuemaxx.outcomes.schema import MatchSpec, OutcomeRule
from valuemaxx.outcomes.signal import SystemSignalClassMapper

_TENANT = TenantId(uuid4())


class _FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 6, 27, tzinfo=UTC)


class _SeqUuid:
    def __init__(self) -> None:
        self._n = 0

    def new(self) -> str:
        self._n += 1
        return f"o-{self._n}"


@pytest.fixture
def host_module() -> types.ModuleType:
    """A throwaway host module with a function we can patch and a 'raiser'."""
    mod = types.ModuleType("hostapp_loans")

    def update_loan_status(application_id: str, status: str, amount: int) -> dict[str, object]:
        return {"application_id": application_id, "status": status, "amount": amount}

    def explode() -> None:
        raise ValueError("host blew up")

    mod.update_loan_status = update_loan_status  # type: ignore[attr-defined]
    mod.explode = explode  # type: ignore[attr-defined]
    sys.modules["hostapp_loans"] = mod
    yield mod
    sys.modules.pop("hostapp_loans", None)


def _emitter(repo: InMemoryOutcomeEventRepository) -> OutcomeEmitter:
    return OutcomeEmitter(
        repository=repo,
        mapper=SystemSignalClassMapper(),
        clock=_FixedClock(),
        uuid_gen=_SeqUuid(),
    )


def _rule(**over: object) -> OutcomeRule:
    base: dict[str, object] = {
        "name": "loan_funded",
        "match": MatchSpec(
            function="hostapp_loans.update_loan_status", when="args.status == 'funded'"
        ),
        "value": "args.amount",
        "bind": {"application_id": "args.application_id"},
        "signal": SignalClass.OUTCOME_CONFIRMED.value,
    }
    base.update(over)
    return OutcomeRule(**base)  # type: ignore[arg-type]


def test_predicate_true_emits_outcome(host_module: types.ModuleType) -> None:
    """When the predicate matches the call, an outcome is emitted (action_attempted)."""
    repo = InMemoryOutcomeEventRepository()
    install_function_rules([_rule()], emitter=_emitter(repo), tenant_id=_TENANT)
    host_module.update_loan_status("app-1", "funded", 1000)
    events = repo.all_for_tenant(_TENANT)
    assert len(events) == 1
    # function match: system clamps the declared 'confirmed' to action_attempted.
    assert events[0].signal_class is SignalClass.ACTION_ATTEMPTED
    assert events[0].value == Decimal("1000")
    assert ("application_id", "app-1") in events[0].entity_keys


def test_predicate_false_does_not_emit(host_module: types.ModuleType) -> None:
    """When the predicate does not match, nothing is emitted."""
    repo = InMemoryOutcomeEventRepository()
    install_function_rules([_rule()], emitter=_emitter(repo), tenant_id=_TENANT)
    host_module.update_loan_status("app-1", "pending", 1000)
    assert repo.all_for_tenant(_TENANT) == ()


def test_host_return_value_is_passed_through(host_module: types.ModuleType) -> None:
    """The wrapped function still returns the host's real value."""
    repo = InMemoryOutcomeEventRepository()
    install_function_rules([_rule()], emitter=_emitter(repo), tenant_id=_TENANT)
    result = host_module.update_loan_status("app-1", "funded", 1000)
    assert result == {"application_id": "app-1", "status": "funded", "amount": 1000}


def test_run_id_bound_from_active_context(host_module: types.ModuleType) -> None:
    """The emitted outcome binds the ambient run_id from contextvars."""
    repo = InMemoryOutcomeEventRepository()
    install_function_rules([_rule()], emitter=_emitter(repo), tenant_id=_TENANT)
    token = active_run_id.set(RunId("run-99"))
    try:
        host_module.update_loan_status("app-1", "funded", 1000)
    finally:
        active_run_id.reset(token)
    assert repo.all_for_tenant(_TENANT)[0].binding.run_id == RunId("run-99")


def test_host_exception_is_not_swallowed(host_module: types.ModuleType) -> None:
    """A host exception propagates unchanged — instrumentation never hides host errors."""
    repo = InMemoryOutcomeEventRepository()
    rule = _rule(
        name="boom",
        match=MatchSpec(function="hostapp_loans.explode", when="True"),
        value=None,
        bind={},
        signal=SignalClass.ACTION_ATTEMPTED.value,
    )
    install_function_rules([rule], emitter=_emitter(repo), tenant_id=_TENANT)
    with pytest.raises(ValueError, match="host blew up"):
        host_module.explode()
    # the host raised, so no outcome is emitted
    assert repo.all_for_tenant(_TENANT) == ()


def test_predicate_error_fails_open(host_module: types.ModuleType) -> None:
    """A predicate that errors at eval time does not break the host call."""
    repo = InMemoryOutcomeEventRepository()
    # arithmetic over a string operand raises inside the predicate at call time
    rule = _rule(
        match=MatchSpec(function="hostapp_loans.update_loan_status", when="args.status + 1 == 2"),
    )
    install_function_rules([rule], emitter=_emitter(repo), tenant_id=_TENANT)
    # host call still returns; emission is simply skipped
    result = host_module.update_loan_status("app-1", "funded", 1000)
    assert result["status"] == "funded"
    assert repo.all_for_tenant(_TENANT) == ()


def test_unresolved_function_target_warns_not_raises() -> None:
    """A non-importable function target is reported (warning), never a silent no-op/crash."""
    repo = InMemoryOutcomeEventRepository()
    rule = _rule(match=MatchSpec(function="nope.does_not_exist", when="True"))
    report = install_function_rules([rule], emitter=_emitter(repo), tenant_id=_TENANT)
    assert "nope.does_not_exist" in report.unresolved


def test_float_value_is_coerced_to_decimal(host_module: types.ModuleType) -> None:
    """A float-valued extractor is coerced to an exact Decimal via str()."""
    repo = InMemoryOutcomeEventRepository()

    def with_float(amount: float) -> dict[str, object]:
        return {"amount": amount}

    host_module.with_float = with_float  # type: ignore[attr-defined]
    rule = _rule(
        name="floaty",
        match=MatchSpec(function="hostapp_loans.with_float", when="True"),
        value="args.amount",
        bind={},
    )
    install_function_rules([rule], emitter=_emitter(repo), tenant_id=_TENANT)
    host_module.with_float(12.5)
    assert repo.all_for_tenant(_TENANT)[0].value == Decimal("12.5")


def test_non_numeric_value_becomes_none(host_module: types.ModuleType) -> None:
    """A non-numeric value extractor yields a None monetary value (never crashes)."""
    repo = InMemoryOutcomeEventRepository()
    rule = _rule(
        name="texty",
        match=MatchSpec(function="hostapp_loans.update_loan_status", when="True"),
        value="args.status",  # a string, not a number
        bind={},
    )
    install_function_rules([rule], emitter=_emitter(repo), tenant_id=_TENANT)
    host_module.update_loan_status("app-1", "funded", 1000)
    assert repo.all_for_tenant(_TENANT)[0].value is None


def test_unintrospectable_callable_falls_back_to_positional(host_module: types.ModuleType) -> None:
    """A builtin-like callable with no signature still captures via positional fallback."""
    repo = InMemoryOutcomeEventRepository()
    # functools.partial of a builtin tends to be unintrospectable; use a C builtin wrapper.
    host_module.builtin_like = len  # type: ignore[attr-defined]
    rule = _rule(
        name="lenrule",
        match=MatchSpec(function="hostapp_loans.builtin_like", when="result == 3"),
        value=None,
        bind={},
        signal=SignalClass.ACTION_ATTEMPTED.value,
    )
    install_function_rules([rule], emitter=_emitter(repo), tenant_id=_TENANT)
    assert host_module.builtin_like([1, 2, 3]) == 3
    assert len(repo.all_for_tenant(_TENANT)) == 1


def test_decimal_value_passes_through(host_module: types.ModuleType) -> None:
    """A value that is already a Decimal passes through unchanged."""
    repo = InMemoryOutcomeEventRepository()

    def with_decimal() -> dict[str, object]:
        return {"amount": Decimal("9.99")}

    host_module.with_decimal = with_decimal  # type: ignore[attr-defined]
    rule = _rule(
        name="dec",
        match=MatchSpec(function="hostapp_loans.with_decimal", when="True"),
        value="result.amount",
        bind={},
    )
    install_function_rules([rule], emitter=_emitter(repo), tenant_id=_TENANT)
    host_module.with_decimal()
    assert repo.all_for_tenant(_TENANT)[0].value == Decimal("9.99")


def test_list_value_becomes_none(host_module: types.ModuleType) -> None:
    """A list-valued extractor yields None (not a money value, never a crash)."""
    repo = InMemoryOutcomeEventRepository()

    def with_list() -> dict[str, object]:
        return {"items": [1, 2, 3]}

    host_module.with_list = with_list  # type: ignore[attr-defined]
    rule = _rule(
        name="lst",
        match=MatchSpec(function="hostapp_loans.with_list", when="True"),
        value="result.items",
        bind={},
    )
    install_function_rules([rule], emitter=_emitter(repo), tenant_id=_TENANT)
    host_module.with_list()
    assert repo.all_for_tenant(_TENANT)[0].value is None


def test_non_function_rules_are_ignored(host_module: types.ModuleType) -> None:
    """install_function_rules only patches function matches; webhook rules are skipped."""
    repo = InMemoryOutcomeEventRepository()
    webhook_rule = _rule(
        name="paid",
        match=MatchSpec(webhook="stripe", event="payment_intent.succeeded"),
        value="data.object.amount",
        bind={},
    )
    report = install_function_rules([webhook_rule], emitter=_emitter(repo), tenant_id=_TENANT)
    assert report.installed == ()
    assert report.unresolved == ()
