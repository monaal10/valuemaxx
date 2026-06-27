"""valuemaxx.outcomes — declarative outcome capture (§6).

The G2 outcomes package: it turns a small, reviewable ``outcomes.yaml`` into live
instrumentation that emits signal-classed, attributable :class:`~valuemaxx.core.OutcomeEvent`\\ s.

* **OUT-A** — the rule schema (:mod:`~valuemaxx.outcomes.schema`) + safe loader
  (:func:`~valuemaxx.outcomes.loader.load_rules`, ``yaml.safe_load`` only) and the AST
  allowlist validator (:class:`~valuemaxx.outcomes.predicate.SafePredicateValidator`,
  never ``eval``).
* **OUT-B** — ``wrapt`` function patching
  (:func:`~valuemaxx.outcomes.instrument.install_function_rules`) and the system-owned
  emitter (:class:`~valuemaxx.outcomes.instrument.OutcomeEmitter`, function/HTTP never
  ``outcome_confirmed``).
* **OUT-C** — T3 ``run_id`` injection
  (:func:`~valuemaxx.outcomes.instrument.install_run_id_injection`, copy-on-write merge
  + init-ordering warning).
* **OUT-D** — webhook ingest (:func:`~valuemaxx.outcomes.webhook.receive_webhook`,
  verify-before-parse, T3 echo / T4 fallback).
* **OUT-E** — retraction (:func:`~valuemaxx.outcomes.retraction.retract_outcome`) and
  capability registration (:func:`~valuemaxx.outcomes.capabilities.register`).

Depends only on ``valuemaxx.core`` (ABCs/Protocols/domain types) and
``valuemaxx.capabilities`` (the registry contract) — never a sibling logic package
nor ``valuemaxx.store`` (the storage port is the :class:`~valuemaxx.core.OutcomeEventRepository`
ABC; an in-memory stub serves this package's own tests).
"""

from __future__ import annotations

from valuemaxx.outcomes.capabilities import register
from valuemaxx.outcomes.errors import (
    OutcomeRuleError,
    OutcomeRuleSchemaError,
    PredicateValidationError,
)
from valuemaxx.outcomes.instrument import (
    EmitRequest,
    FunctionInstallReport,
    InjectionReport,
    OutcomeEmitter,
    install_function_rules,
    install_run_id_injection,
)
from valuemaxx.outcomes.loader import load_rules
from valuemaxx.outcomes.predicate import (
    SafePredicateValidator,
    compile_expr,
    compile_predicate,
)
from valuemaxx.outcomes.retraction import RetractionResult, retract_outcome
from valuemaxx.outcomes.schema import MatchSpec, OutcomeRule, RunIdInjectionSpec
from valuemaxx.outcomes.signal import SystemSignalClassMapper
from valuemaxx.outcomes.webhook import (
    WebhookRequest,
    WebhookSecurity,
    WebhookSignatureError,
    receive_webhook,
)

__all__ = [
    "EmitRequest",
    "FunctionInstallReport",
    "InjectionReport",
    "MatchSpec",
    "OutcomeEmitter",
    "OutcomeRule",
    "OutcomeRuleError",
    "OutcomeRuleSchemaError",
    "PredicateValidationError",
    "RetractionResult",
    "RunIdInjectionSpec",
    "SafePredicateValidator",
    "SystemSignalClassMapper",
    "WebhookRequest",
    "WebhookSecurity",
    "WebhookSignatureError",
    "compile_expr",
    "compile_predicate",
    "install_function_rules",
    "install_run_id_injection",
    "load_rules",
    "receive_webhook",
    "register",
    "retract_outcome",
]
