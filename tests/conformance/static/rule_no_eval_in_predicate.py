"""no_eval_in_predicate — the outcome predicate DSL never eval/exec/dunders (GREEN; owner OUTCOMES).

The outcomes package compiles ``when``/``value``/``bind`` expressions with an AST
allowlist interpreter and never calls the builtin ``eval``/``exec``; an expression using
such a construct is rejected at author time. ``flags_violation`` scans a python source
string for the forbidden markers. The negative fixture is a synthetic violation; the
foundation subject is the real predicate evaluator source, which contains no such call
(the DSL is interpreted, never executed).
"""

from __future__ import annotations

from tests.conformance.astutil import package_src
from tests.conformance.rulebase import Rule, RuleKind

_MARKERS: tuple[str, ...] = ("eval(", "exec(", "__import__", "__globals__")


def _flags(subject: object) -> bool:
    assert isinstance(subject, str)
    return any(marker in subject for marker in _MARKERS)


def _negative_fixture() -> object:
    return "eval(user_predicate)\n"


def _foundation_subject() -> object:
    # The real predicate evaluator: an AST allowlist interpreter, never an eval/exec call.
    return (package_src("outcomes") / "predicate.py").read_text()


def metrics_dsl_has_no_eval() -> list[str]:
    """Scan the metrics DSL/compiler sources; return files containing an eval/exec marker.

    The metric mini-DSL is a typed closed allowlist (a membership check, never an
    interpreter), so neither the grammar nor the pure compiler may carry an
    ``eval``/``exec``/dunder-reflection marker. METRICS turns this rule green for
    its own surface (the build plan lists OUTCOMES and METRICS as joint owners).
    """
    offenders: list[str] = []
    metrics_src = package_src("metrics")
    for module in ("grammar.py", "compiler.py", "executor.py"):
        path = metrics_src / module
        if path.exists() and _flags(path.read_text()):
            offenders.append(str(path))
    return offenders


RULE = Rule(
    name="no_eval_in_predicate",
    kind=RuleKind.STATIC,
    green_now=True,
    owner_task="OUTCOMES",
    flags_violation=_flags,
    negative_fixture=_negative_fixture,
    foundation_subject=_foundation_subject,
)
