"""OUT-A: the safe predicate validator + compiler (AST allowlist, no eval/exec/dunder)."""

from __future__ import annotations

import pytest
from valuemaxx.core import OutcomesPredicateValidator
from valuemaxx.outcomes.errors import PredicateValidationError
from valuemaxx.outcomes.predicate import (
    SafePredicateValidator,
    compile_expr,
    compile_predicate,
)


def test_validator_satisfies_core_protocol() -> None:
    """SafePredicateValidator structurally satisfies the core Protocol."""
    assert isinstance(SafePredicateValidator(), OutcomesPredicateValidator)


def test_validate_accepts_simple_comparison() -> None:
    """A plain comparison over attribute reads validates cleanly."""
    SafePredicateValidator().validate("args.status == 'funded'")


@pytest.mark.parametrize(
    "expr",
    [
        "eval('1+1')",
        "exec('x=1')",
        "__import__('os').system('rm -rf /')",
        "args.__class__",
        "args.__globals__",
        "(1).__class__.__bases__",
        "open('/etc/passwd')",
        "args.status.__dict__",
    ],
)
def test_validate_rejects_dangerous_constructs(expr: str) -> None:
    """eval/exec/dunder/unknown-call constructs all raise."""
    with pytest.raises(PredicateValidationError):
        SafePredicateValidator().validate(expr)


def test_validate_rejects_unparseable() -> None:
    """A syntactically invalid predicate raises (not a silent pass)."""
    with pytest.raises(PredicateValidationError):
        SafePredicateValidator().validate("args.status ==")


def test_compile_predicate_evaluates_true_false() -> None:
    """compile_predicate returns a callable over the namespace mapping."""
    pred = compile_predicate("args.status == 'funded'")
    assert pred({"args": {"status": "funded"}}) is True
    assert pred({"args": {"status": "pending"}}) is False


def test_compile_predicate_supports_boolean_and_membership() -> None:
    """Boolean ops and membership are allowed (and gate emission)."""
    pred = compile_predicate("args.status == 'funded' and result.ok")
    assert pred({"args": {"status": "funded"}, "result": {"ok": True}}) is True
    assert pred({"args": {"status": "funded"}, "result": {"ok": False}}) is False

    member = compile_predicate("args.kind in ('a', 'b')")
    assert member({"args": {"kind": "a"}}) is True
    assert member({"args": {"kind": "z"}}) is False


def test_compile_expr_extracts_value_via_attribute_path() -> None:
    """compile_expr reads a value out of the namespace without eval."""
    extractor = compile_expr("args.amount")
    assert extractor({"args": {"amount": 1000}}) == 1000

    nested = compile_expr("data.object.metadata.run_id")
    assert nested({"data": {"object": {"metadata": {"run_id": "run-42"}}}}) == "run-42"


def test_compiled_predicate_never_uses_builtin_eval() -> None:
    """A compiled predicate cannot reach builtins (no eval/exec in scope)."""
    pred = compile_predicate("args.ok == True")
    # missing attribute resolves to None, never raising into the host
    assert pred({"args": {}}) is False


def test_compile_predicate_ordering_and_arithmetic() -> None:
    """Ordering comparisons and arithmetic evaluate over numeric values."""
    assert compile_predicate("args.amount >= 1000")({"args": {"amount": 1000}}) is True
    assert compile_predicate("args.amount > 1000")({"args": {"amount": 1000}}) is False
    assert compile_predicate("args.a < args.b")({"args": {"a": 1, "b": 2}}) is True
    assert compile_predicate("args.a <= args.b")({"args": {"a": 2, "b": 2}}) is True
    assert compile_expr("args.a + args.b")({"args": {"a": 2, "b": 3}}) == 5
    assert compile_expr("args.a - args.b")({"args": {"a": 5, "b": 3}}) == 2
    assert compile_expr("args.a * args.b")({"args": {"a": 4, "b": 3}}) == 12
    assert compile_expr("args.a / args.b")({"args": {"a": 6, "b": 3}}) == 2
    assert compile_expr("args.a % args.b")({"args": {"a": 7, "b": 3}}) == 1


def test_compile_predicate_string_ordering() -> None:
    """Two strings compare lexicographically."""
    assert compile_predicate("args.s < 'b'")({"args": {"s": "a"}}) is True


def test_compile_predicate_unary_and_not() -> None:
    """Unary minus/plus over a number and boolean not all evaluate."""
    assert compile_expr("-args.n")({"args": {"n": 5}}) == -5
    assert compile_expr("+args.n")({"args": {"n": 5}}) == 5
    assert compile_predicate("not result.ok")({"result": {"ok": False}}) is True


def test_compile_predicate_membership_over_string_and_list() -> None:
    """Membership works over a list value and a string (substring) value."""
    pred = compile_predicate("args.k in args.allowed")
    assert pred({"args": {"k": "x", "allowed": ["x", "y"]}}) is True
    assert pred({"args": {"k": "z", "allowed": ["x", "y"]}}) is False
    not_in = compile_predicate("args.k not in ('x', 'y')")
    assert not_in({"args": {"k": "z"}}) is True
    substr = compile_predicate("args.frag in args.text")
    assert substr({"args": {"frag": "oo", "text": "food"}}) is True


def test_compile_predicate_membership_in_non_container_is_false() -> None:
    """Membership against a non-container value is False, never an error."""
    pred = compile_predicate("args.k in args.n")
    assert pred({"args": {"k": "x", "n": 5}}) is False


def test_subscript_read_over_object_attribute() -> None:
    """Subscripting a non-mapping object reads the attribute of that name."""

    class _Box:
        status = "funded"

    assert compile_expr("args['status']")({"args": _Box()}) == "funded"


def test_arithmetic_on_non_numeric_raises_inside_predicate() -> None:
    """Arithmetic over non-numeric operands raises (caught by the fail-open caller)."""
    bad = compile_expr("args.a + args.b")
    with pytest.raises(PredicateValidationError):
        bad({"args": {"a": "x", "b": 1}})


def test_unary_minus_on_non_numeric_raises() -> None:
    """Unary minus over a non-number raises (caught by the fail-open caller)."""
    bad = compile_expr("-args.s")
    with pytest.raises(PredicateValidationError):
        bad({"args": {"s": "x"}})


def test_ordering_on_incomparable_raises() -> None:
    """Ordering a number against a string raises (no silent surprising coercion)."""
    bad = compile_predicate("args.a < args.b")
    with pytest.raises(PredicateValidationError):
        bad({"args": {"a": 1, "b": "x"}})


def test_validate_rejects_call_and_lambda_and_walrus() -> None:
    """Calls, lambdas, and walrus assignments are not in the allowlist."""
    v = SafePredicateValidator()
    for expr in ("foo()", "args.f()", "lambda x: x", "(x := 1)"):
        with pytest.raises(PredicateValidationError):
            v.validate(expr)


def test_constant_names_validate_and_evaluate() -> None:
    """True/False/None pass validation as names and evaluate to their constants."""
    assert compile_expr("True")({}) is True
    assert compile_expr("False")({}) is False
    assert compile_expr("None")({}) is None
    assert compile_predicate("result.ok == None")({"result": {"ok": None}}) is True


def test_subscript_over_mapping_value() -> None:
    """Subscripting a mapping reads by key (not attribute)."""
    assert compile_expr("data['amount']")({"data": {"amount": 1000}}) == 1000


def test_boolean_or_evaluates() -> None:
    """A boolean OR short-circuits to True when either side is truthy."""
    pred = compile_predicate("result.a or result.b")
    assert pred({"result": {"a": False, "b": True}}) is True
    assert pred({"result": {"a": False, "b": False}}) is False


def test_read_rejects_dunder_via_runtime_subscript_key() -> None:
    """A dunder reached through a runtime subscript key over an object is rejected."""

    class _Obj:
        k = "__class__"

    bad = compile_expr("args[args.k]")
    with pytest.raises(PredicateValidationError):
        bad({"args": _Obj()})
