"""OUT-A: the safe predicate DSL — an AST allowlist evaluator, never ``eval``/``exec``.

An outcome rule's ``when`` predicate and ``value``/``bind`` extractors are tiny
expressions over a fixed namespace (``args``, ``kwargs``, ``result``, ``data`` ...).
They are **never** passed to the builtin :func:`eval`. Instead each expression is
parsed with :mod:`ast`, validated against a strict allowlist (comparisons, boolean
ops, attribute/subscript reads, literals, membership), and then walked by a pure
interpreter (:func:`_eval_node`) that has no access to builtins, imports, calls, or
dunder attributes. Anything outside the allowlist raises
:class:`~valuemaxx.outcomes.errors.PredicateValidationError` at author time — this is
the executable form of the ``no_eval_in_predicate`` conformance rule.

Attribute and subscript reads are unified: ``args.status`` and ``args['status']``
both read the ``status`` key/attr of ``args``. A missing key/attribute resolves to
``None`` (never an exception into the host), so a predicate over absent data is
simply falsy rather than crashing the instrumented call.
"""

from __future__ import annotations

import ast
import operator
from collections.abc import Callable, Mapping
from typing import Final, cast

from valuemaxx.outcomes.errors import PredicateValidationError

# The namespace a predicate may read. A Name outside this set is rejected at
# validation time (no free variables -> no way to reach builtins/globals).
_ALLOWED_ROOTS: Final[frozenset[str]] = frozenset(
    {"args", "kwargs", "result", "data", "instance", "event"}
)

_CONST_NAMES: Final[Mapping[str, object]] = {"True": True, "False": False, "None": None}

# Only these AST node types may appear anywhere in a predicate/extractor.
_ALLOWED_NODES: Final[tuple[type[ast.AST], ...]] = (
    ast.Expression,
    ast.BoolOp,
    ast.And,
    ast.Or,
    ast.UnaryOp,
    ast.Not,
    ast.USub,
    ast.UAdd,
    ast.BinOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Mod,
    ast.Compare,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,
    ast.NotIn,
    ast.Name,
    ast.Load,
    ast.Attribute,
    ast.Subscript,
    ast.Constant,
    ast.Tuple,
    ast.List,
)

_BinaryOp = Callable[[object, object], object]

# eq/ne accept object directly. Ordering and arithmetic operate on numeric/comparable
# predicate values; they are wrapped in helpers with an honest (object, object) ->
# object signature. Non-numeric inputs raise, which the fail-open instrumentation
# path catches — they never propagate into the host call.
_COMPARE_OPS: Final[Mapping[type[ast.cmpop], _BinaryOp]] = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: lambda a, b: _order(a, b) < 0,
    ast.LtE: lambda a, b: _order(a, b) <= 0,
    ast.Gt: lambda a, b: _order(a, b) > 0,
    ast.GtE: lambda a, b: _order(a, b) >= 0,
}

_BIN_OPS: Final[Mapping[type[ast.operator], _BinaryOp]] = {
    ast.Add: lambda a, b: _arith(operator.add, a, b),
    ast.Sub: lambda a, b: _arith(operator.sub, a, b),
    ast.Mult: lambda a, b: _arith(operator.mul, a, b),
    ast.Div: lambda a, b: _arith(lambda x, y: x / y, a, b),
    ast.Mod: lambda a, b: _arith(operator.mod, a, b),
}


def _order(left: object, right: object) -> int:
    """Three-way compare for ordered operands; raise on incomparable values."""
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return (left > right) - (left < right)
    if isinstance(left, str) and isinstance(right, str):
        return (left > right) - (left < right)
    raise PredicateValidationError("ordered comparison requires two numbers or two strings")


def _arith(op: Callable[[float, float], float], left: object, right: object) -> object:
    """Apply a numeric binary op; raise on non-numeric operands."""
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return op(left, right)
    raise PredicateValidationError("arithmetic requires numeric operands")


Namespace = Mapping[str, object]
Predicate = Callable[[Namespace], bool]
Extractor = Callable[[Namespace], object]


def _parse(expr: str) -> ast.Expression:
    """Parse ``expr`` in ``eval`` mode; reject anything unparseable or disallowed."""
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise PredicateValidationError(f"unparseable predicate {expr!r}: {exc}") from exc
    _validate_tree(tree)
    return tree


def _validate_tree(tree: ast.Expression) -> None:
    """Walk the whole tree; reject any node, name, or attribute outside the allowlist."""
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise PredicateValidationError(
                f"predicate uses a disallowed construct: {type(node).__name__}"
            )
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise PredicateValidationError(f"dunder attribute access is forbidden: {node.attr!r}")
        if isinstance(node, ast.Name) and node.id not in _ALLOWED_ROOTS:
            if node.id in _CONST_NAMES:
                continue
            raise PredicateValidationError(
                f"predicate references unknown name {node.id!r}; "
                f"only {sorted(_ALLOWED_ROOTS)} are in scope"
            )


def _read(container: object, key: str) -> object:
    """Read ``key`` from a mapping (by key) or object (by attribute); missing -> None.

    Never dereferences a dunder and never raises into the host: an absent field
    makes the surrounding predicate falsy rather than crashing the instrumented call.
    """
    if key.startswith("__"):
        raise PredicateValidationError(f"dunder access is forbidden: {key!r}")
    if isinstance(container, Mapping):
        return _mapping_get(cast("Mapping[object, object]", container), key)
    return getattr(container, key, None)


def _mapping_get(container: Mapping[object, object], key: object) -> object:
    """Read a key from a mapping, returning None when absent (typed helper)."""
    return container.get(key)


def _eval_node(node: ast.AST, ns: Namespace) -> object:
    """Pure interpreter over the validated AST — no builtins, no calls, no imports."""
    if isinstance(node, ast.Expression):
        return _eval_node(node.body, ns)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in _CONST_NAMES:
            return _CONST_NAMES[node.id]
        return ns.get(node.id)
    if isinstance(node, ast.Attribute):
        return _read(_eval_node(node.value, ns), node.attr)
    if isinstance(node, ast.Subscript):
        target = _eval_node(node.value, ns)
        key = _eval_node(node.slice, ns)
        if isinstance(target, Mapping):
            return _mapping_get(cast("Mapping[object, object]", target), key)
        return _read(target, str(key))
    if isinstance(node, (ast.Tuple, ast.List)):
        return [_eval_node(elt, ns) for elt in node.elts]
    if isinstance(node, ast.BoolOp):
        values = [_eval_node(v, ns) for v in node.values]
        if isinstance(node.op, ast.And):
            return all(values)
        return any(values)
    if isinstance(node, ast.UnaryOp):
        return _eval_unary(node, ns)
    if isinstance(node, ast.BinOp):
        return _eval_bin(node, ns)
    if isinstance(node, ast.Compare):
        return _eval_compare(node, ns)
    # Unreachable: _validate_tree rejected anything not handled above.
    name = type(node).__name__
    raise PredicateValidationError(f"cannot evaluate node {name}")  # pragma: no cover


def _eval_unary(node: ast.UnaryOp, ns: Namespace) -> object:
    operand = _eval_node(node.operand, ns)
    if isinstance(node.op, ast.Not):
        return not operand
    if not isinstance(operand, (int, float)):
        raise PredicateValidationError("unary +/- requires a numeric operand")
    if isinstance(node.op, ast.USub):
        return -operand
    return +operand  # ast.UAdd


def _eval_bin(node: ast.BinOp, ns: Namespace) -> object:
    op = _BIN_OPS[type(node.op)]
    return op(_eval_node(node.left, ns), _eval_node(node.right, ns))


def _eval_compare(node: ast.Compare, ns: Namespace) -> bool:
    left = _eval_node(node.left, ns)
    for op_node, comparator in zip(node.ops, node.comparators, strict=True):
        right = _eval_node(comparator, ns)
        result: object
        if isinstance(op_node, ast.In):
            result = _contains(right, left)
        elif isinstance(op_node, ast.NotIn):
            result = not _contains(right, left)
        else:
            result = _COMPARE_OPS[type(op_node)](left, right)
        if not result:
            return False
        left = right
    return True


def _contains(container: object, item: object) -> bool:
    """Membership over a list/tuple/set/str container; non-containers are never members."""
    if isinstance(container, str):
        return isinstance(item, str) and item in container
    if isinstance(container, (list, tuple, set, frozenset)):
        members: tuple[object, ...] = tuple(cast("tuple[object, ...]", container))
        return item in members
    return False


def compile_predicate(expr: str) -> Predicate:
    """Validate ``expr`` and return a callable that evaluates it to a strict ``bool``."""
    tree = _parse(expr)

    def _predicate(ns: Namespace) -> bool:
        return bool(_eval_node(tree, ns))

    return _predicate


def compile_expr(expr: str) -> Extractor:
    """Validate ``expr`` and return a callable that extracts its value (``value``/``bind``)."""
    tree = _parse(expr)

    def _extractor(ns: Namespace) -> object:
        return _eval_node(tree, ns)

    return _extractor


class SafePredicateValidator:
    """The :class:`~valuemaxx.core.OutcomesPredicateValidator` implementation (§6.1).

    Validates a predicate/extractor expression against the AST allowlist, raising
    :class:`~valuemaxx.outcomes.errors.PredicateValidationError` on ``eval``/``exec``/
    dunder/unknown constructs. It never executes the expression — only parses and
    inspects it — so calling ``validate`` is side-effect-free.
    """

    def validate(self, expr: str) -> None:
        """Validate ``expr``; raise :class:`PredicateValidationError` if disallowed."""
        _parse(expr)


__all__ = [
    "Extractor",
    "Namespace",
    "Predicate",
    "SafePredicateValidator",
    "compile_expr",
    "compile_predicate",
]
