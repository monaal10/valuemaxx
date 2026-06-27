"""In-memory stubs of the core C3 Protocols, for onboarding tests.

These implement the ``valuemaxx.core`` Protocols (``SignalClassMapper``,
``OutcomesPredicateValidator``) and the local ``MetricsRollupReader`` Protocol the
onboarding package depends on. The onboarding code is written against the Protocols,
never these concretes — the stubs exist only so the tests can exercise the seams
without importing a sibling logic package or the store.
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from valuemaxx.onboarding.errors import UnsafePredicateError

if TYPE_CHECKING:
    from valuemaxx.onboarding.capabilities import CostPerOutcome


class StubSignalMapper:
    """Maps a match to its system-owned signal class (the ``SignalClassMapper`` seam).

    Authoritative status transitions / external writes / webhooks confirm an outcome;
    a bare function/HTTP attempt is only ``action_attempted`` (never user-upgraded).
    """

    def map_signal(self, *, match_kind: str, declared: str) -> str:
        _ = declared  # declared is advisory only; the system owns the result
        if match_kind in {"status_setter", "mark_function", "orm_write", "webhook"}:
            return "outcome_confirmed"
        if match_kind == "external_write":
            return "action_attempted"
        return "action_attempted"


class StubPredicateValidator:
    """A safe-predicate validator (the ``OutcomesPredicateValidator`` seam).

    Rejects ``eval``/``exec``/``__`` dunder access; accepts plain comparisons. This is
    a deliberately small stand-in for the real outcomes validator (which onboarding
    must not import).
    """

    def validate(self, expr: str) -> None:
        tree = ast.parse(expr, mode="eval")
        for node in ast.walk(tree):
            bad_call = isinstance(node, ast.Call)
            bad_dunder = isinstance(node, ast.Attribute) and node.attr.startswith("__")
            bad_name = isinstance(node, ast.Name) and node.id in {"eval", "exec", "__import__"}
            if bad_call or bad_dunder or bad_name:
                raise UnsafePredicateError(f"disallowed construct: {type(node).__name__}")


class StubRollupReader:
    """An in-memory ``MetricsRollupReader`` returning a fixed cost-per-outcome.

    Stands in for the real metrics/store-backed reader (which onboarding must not
    import); the dry-run code is written against the Protocol, not this concrete.
    """

    def __init__(self, result: CostPerOutcome | None) -> None:
        self._result = result

    def cost_per_outcome(self, *, outcome_name: str) -> CostPerOutcome | None:
        _ = outcome_name
        return self._result
