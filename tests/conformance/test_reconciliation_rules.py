"""Substantive RECON-side check for the ``additive_reconciliation`` rule (§5.3, §3.1).

The ``additive_reconciliation`` rule (``static/rule_additive_reconciliation.py``) is
co-owned STORE/RECON: STORE turns it green against the append-only repository, and
RECON keeps the *service* honest. Reconciliation is an additive
:class:`~valuemaxx.core.ReconciliationRecord` and never an UPDATE to an estimate, so
the reconciliation service must expose / call no estimate-mutating path.

This test exercises the live RECON-side invariant beyond the rule's foundation
subject: it AST-scans the reconciliation service for any mutate-shaped call, and
confirms the package's only reconciliation write port (the append-only
:class:`~valuemaxx.reconciliation.service.ReconciliationAppender`) has no update method.
"""

from __future__ import annotations

import ast

import pytest

from tests.conformance.astutil import package_src

_FORBIDDEN = ("update", "mutate", "replace", "overwrite", "patch", "set_cost", "delete")


def _service_source() -> str:
    return (package_src("reconciliation") / "service.py").read_text()


@pytest.mark.conformance
def test_reconciliation_service_calls_no_mutate_path() -> None:
    """The reconciliation service never calls an estimate-mutating method."""
    tree = ast.parse(_service_source())
    called_attrs = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    offenders = {attr for attr in called_attrs if any(m in attr.lower() for m in _FORBIDDEN)}
    assert offenders == set(), f"reconciliation service calls a mutate path: {offenders}"


@pytest.mark.conformance
def test_reconciliation_append_port_has_no_update_method() -> None:
    """The reconciliation write port exposes only ``append`` (no update/mutate)."""
    from valuemaxx.reconciliation.service import ReconciliationAppender

    methods = {name for name in dir(ReconciliationAppender) if not name.startswith("_")}
    assert methods == {"append"}, f"unexpected write-port methods: {methods}"
    assert not any(any(m in name.lower() for m in _FORBIDDEN) for name in methods)
