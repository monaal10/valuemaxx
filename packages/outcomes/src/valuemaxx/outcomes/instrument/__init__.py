"""OUT-B/OUT-C: live instrumentation — function patching, emission, and run_id injection.

This sub-package owns the runtime side of outcome capture: ``wrapt`` patches of declared
functions/HTTP/ORM-save sites (:mod:`~valuemaxx.outcomes.instrument.functions`), the
:class:`~valuemaxx.outcomes.instrument.emitter.OutcomeEmitter` that turns a match into a
signal-classed :class:`~valuemaxx.core.OutcomeEvent`, and the T3 ``run_id`` injection
wrappers (:mod:`~valuemaxx.outcomes.instrument.injection`). Every path fails open: an
internal error is logged and dropped, never propagated into the instrumented host call.
"""

from __future__ import annotations

from valuemaxx.outcomes.instrument.emitter import EmitRequest, OutcomeEmitter
from valuemaxx.outcomes.instrument.functions import (
    FunctionInstallReport,
    install_function_rules,
)
from valuemaxx.outcomes.instrument.injection import (
    InjectionReport,
    install_run_id_injection,
)

__all__ = [
    "EmitRequest",
    "FunctionInstallReport",
    "InjectionReport",
    "OutcomeEmitter",
    "install_function_rules",
    "install_run_id_injection",
]
