"""OUT-B: install ``wrapt`` patches for declared function/HTTP/ORM-save outcome rules.

:func:`install_function_rules` wraps each declared in-process match target with a
``wrapt`` function wrapper. The wrapper runs the host call first, then — *only after* a
successful return — evaluates the compiled ``when`` predicate over a namespace of
``{args, kwargs, result}`` and, if it matches, emits a signal-classed outcome bound to
the ambient ``run_id`` (from :data:`~valuemaxx.core.active_run_id`).

Two hard invariants (AGENTS.md §5, §6.4):

* **Never swallow the host error.** The predicate/emit work happens *after* the wrapped
  call; if the host raises, the wrapper does nothing and re-raises unchanged.
* **Fail open.** Any error in our own predicate/emit path is logged (secret-safe) and
  dropped — the host's return value is always passed through untouched.

Positional arguments are bound to their parameter names via the wrapped function's
signature, so a predicate written as ``args.status`` reads the ``status`` argument
regardless of whether the caller passed it positionally or by keyword.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import TYPE_CHECKING

import wrapt
from valuemaxx.core import active_run_id
from valuemaxx.outcomes.instrument._resolve import resolve_target
from valuemaxx.outcomes.instrument.emitter import coerce_money
from valuemaxx.outcomes.predicate import compile_expr, compile_predicate
from valuemaxx.outcomes.safelog import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from valuemaxx.core import RunId, TenantId
    from valuemaxx.outcomes.instrument.emitter import OutcomeEmitter
    from valuemaxx.outcomes.predicate import Extractor, Predicate
    from valuemaxx.outcomes.schema import OutcomeRule

_logger = get_logger("valuemaxx.outcomes.functions")

# The match kinds install_function_rules handles (in-process patch targets).
_IN_PROCESS_KINDS = frozenset({"function", "http", "orm_save", "status_transition"})


@dataclass(frozen=True, slots=True)
class FunctionInstallReport:
    """The outcome of installing function rules: what was patched and what couldn't be."""

    installed: tuple[str, ...]
    unresolved: tuple[str, ...]


def install_function_rules(
    rules: Sequence[OutcomeRule],
    *,
    emitter: OutcomeEmitter,
    tenant_id: TenantId,
) -> FunctionInstallReport:
    """Patch every in-process rule target; report installed + unresolved targets.

    Webhook rules are ignored here (they arrive via the webhook receiver). A target that
    is not importable now is recorded in ``unresolved`` and a startup warning is logged —
    never a silent no-op.
    """
    installed: list[str] = []
    unresolved: list[str] = []
    for rule in rules:
        if rule.match.match_kind not in _IN_PROCESS_KINDS:
            continue
        target = rule.match.target
        resolved = resolve_target(target)
        if resolved is None:
            _logger.warning("outcome rule %r target not importable at init: %s", rule.name, target)
            unresolved.append(target)
            continue
        wrapper = _make_wrapper(rule, emitter=emitter, tenant_id=tenant_id)
        wrapt.wrap_function_wrapper(resolved.module_name, resolved.attr_path, wrapper)
        installed.append(target)
    return FunctionInstallReport(installed=tuple(installed), unresolved=tuple(unresolved))


def _make_wrapper(
    rule: OutcomeRule,
    *,
    emitter: OutcomeEmitter,
    tenant_id: TenantId,
) -> Callable[[Callable[..., object], object, tuple[object, ...], dict[str, object]], object]:
    predicate: Predicate | None = (
        compile_predicate(rule.match.when) if rule.match.when is not None else None
    )
    value_expr: Extractor | None = compile_expr(rule.value) if rule.value is not None else None
    bind_exprs: dict[str, Extractor] = {k: compile_expr(v) for k, v in rule.bind.items()}

    def _wrapper(
        wrapped: Callable[..., object],
        _instance: object,
        args: tuple[object, ...],
        kwargs: dict[str, object],
    ) -> object:
        # Host call FIRST — never inside our guard, so its exceptions propagate unchanged.
        result = wrapped(*args, **kwargs)
        try:
            _maybe_emit(
                wrapped,
                args,
                kwargs,
                result,
                rule=rule,
                predicate=predicate,
                value_expr=value_expr,
                bind_exprs=bind_exprs,
                emitter=emitter,
                tenant_id=tenant_id,
            )
        except Exception as exc:  # fail-open: our error must never reach the host caller
            _logger.warning("outcome capture failed for rule %r: %s", rule.name, exc)
        return result

    return _wrapper


def _maybe_emit(
    wrapped: Callable[..., object],
    args: tuple[object, ...],
    kwargs: dict[str, object],
    result: object,
    *,
    rule: OutcomeRule,
    predicate: Predicate | None,
    value_expr: Extractor | None,
    bind_exprs: Mapping[str, Extractor],
    emitter: OutcomeEmitter,
    tenant_id: TenantId,
) -> None:
    from valuemaxx.outcomes.instrument.emitter import EmitRequest

    namespace = _build_namespace(wrapped, args, kwargs, result)
    if predicate is not None and not predicate(namespace):
        return

    value = coerce_money(value_expr(namespace)) if value_expr is not None else None
    entity_keys = frozenset((name, str(expr(namespace))) for name, expr in bind_exprs.items())
    emitter.emit(
        EmitRequest(
            tenant_id=tenant_id,
            name=rule.name,
            match_kind=rule.match.match_kind,
            declared_signal=rule.signal,
            value=value,
            entity_keys=entity_keys,
            correlation_id=None,
            source=rule.match.target,
            run_id=_current_run_id(),
            raw={},
        )
    )


def _build_namespace(
    wrapped: Callable[..., object],
    args: tuple[object, ...],
    kwargs: dict[str, object],
    result: object,
) -> dict[str, object]:
    """Bind positional args to names so ``args.<name>`` works regardless of call style."""
    bound: dict[str, object] = dict(kwargs)
    try:
        signature = inspect.signature(wrapped)
        applied = signature.bind_partial(*args, **kwargs)
        bound = dict(applied.arguments)
    except (TypeError, ValueError):
        # Unintrospectable callable: fall back to positional index keys + kwargs.
        bound = {f"_{i}": value for i, value in enumerate(args)}
        bound.update(kwargs)
    return {"args": bound, "kwargs": dict(kwargs), "result": result}


def _current_run_id() -> RunId | None:
    return active_run_id.get()


__all__ = ["FunctionInstallReport", "install_function_rules"]
