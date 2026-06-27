"""additive_reconciliation —
the reconciliation repository exposes no estimate-mutating method (owner STORE/RECON).

Reconciliation is an additive ``ReconciliationRecord`` and never an UPDATE to an
estimate (§5.3). The guardrail: the concrete reconciliation repository must expose no
method whose name implies mutation (``update``/``mutate``/``replace``/``overwrite``/
``patch``/``delete``). ``flags_violation`` AST-scans a python source string for a
*function/method definition* whose name contains such a fragment — scanning definitions
(not raw substrings) so prose like the docstring's "never an UPDATE" does not false-
positive. The negative fixture is a synthetic repo with an ``update_estimate`` method;
the foundation subject is the real ``PgReconciliationRepository`` source (append-only).
"""

from __future__ import annotations

import ast

from tests.conformance.astutil import package_src
from tests.conformance.rulebase import Rule, RuleKind

_MARKERS: tuple[str, ...] = ("update", "mutate", "replace", "overwrite", "patch", "delete")


def _flags(subject: object) -> bool:
    assert isinstance(subject, str)
    tree = ast.parse(subject)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            name = node.name.lower()
            if any(marker in name for marker in _MARKERS):
                return True
    return False


def _negative_fixture() -> object:
    return "class Repo:\n    def update_estimate(self, x): ...\n"


def _foundation_subject() -> object:
    return (package_src("store") / "repositories" / "reconciliation.py").read_text()


RULE = Rule(
    name="additive_reconciliation",
    kind=RuleKind.STATIC,
    green_now=True,
    owner_task="STORE",
    flags_violation=_flags,
    negative_fixture=_negative_fixture,
    foundation_subject=_foundation_subject,
)
