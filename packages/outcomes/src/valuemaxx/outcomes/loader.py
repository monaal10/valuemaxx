"""OUT-A: parse + validate an ``outcomes.yaml`` document into :class:`OutcomeRule`\\ s.

:func:`load_rules` uses :func:`yaml.safe_load` — **never** :func:`yaml.load` — so a
malicious ``!!python/object`` payload is rejected rather than constructing arbitrary
objects. Every ``when``/``value``/``bind`` expression is validated through the
injected :class:`~valuemaxx.core.OutcomesPredicateValidator` (the AST allowlist) so
no predicate is ever ``eval``'d. The validator is injected, not constructed here, so
the caller (and tests) controls the policy and can spy on what was validated.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import yaml
from valuemaxx.outcomes.errors import OutcomeRuleSchemaError
from valuemaxx.outcomes.schema import MatchSpec, OutcomeRule, RunIdInjectionSpec
from valuemaxx.outcomes.signal import SystemSignalClassMapper

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from valuemaxx.core import OutcomesPredicateValidator

_MATCH_KINDS: tuple[str, ...] = (
    "function",
    "http",
    "orm_save",
    "status_transition",
    "webhook",
)
_INJECTION_KEYS: tuple[str, ...] = ("sdk_call", "inject_into", "webhook_event", "extract_from")


def load_rules(
    text: str,
    *,
    validator: OutcomesPredicateValidator,
) -> tuple[OutcomeRule, ...]:
    """Parse ``text`` (an ``outcomes.yaml`` document) into validated outcome rules.

    Args:
        text: the YAML document source.
        validator: the predicate validator each ``when``/``value``/``bind`` expression
            is checked against (the AST allowlist).

    Returns:
        The declared rules, in document order.

    Raises:
        OutcomeRuleSchemaError: on a structural problem (not a mapping, missing name,
            two match kinds, ``!!python/object`` payload, unknown declared signal, ...).
        PredicateValidationError: on a predicate/extractor outside the AST allowlist.
    """
    document = _safe_parse(text)
    raw_rules = _extract_rule_list(document)
    return tuple(_build_rule(raw, validator) for raw in raw_rules)


def _safe_parse(text: str) -> object:
    """yaml.safe_load with constructor errors surfaced as a schema error (never yaml.load)."""
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise OutcomeRuleSchemaError(f"could not parse outcomes.yaml: {exc}") from exc


def _as_mapping(value: object, where: str) -> Mapping[str, object]:
    """Narrow a yaml node to a string-keyed mapping or raise a schema error."""
    if not isinstance(value, dict):
        raise OutcomeRuleSchemaError(f"{where} must be a mapping; got {type(value).__name__}")
    return cast("Mapping[str, object]", value)


def _as_str(value: object, where: str) -> str:
    if not isinstance(value, str):
        raise OutcomeRuleSchemaError(f"{where} must be a string; got {type(value).__name__}")
    return value


def _extract_rule_list(document: object) -> Sequence[object]:
    doc = _as_mapping(document, "outcomes.yaml")
    raw = doc.get("outcomes")
    if not isinstance(raw, list):
        raise OutcomeRuleSchemaError("'outcomes' must be a list of rule mappings")
    return cast("Sequence[object]", raw)


def _build_rule(raw: object, validator: OutcomesPredicateValidator) -> OutcomeRule:
    rule = _as_mapping(raw, "outcome rule")
    name = rule.get("name")
    if not isinstance(name, str) or not name:
        raise OutcomeRuleSchemaError("each outcome rule needs a non-empty 'name'")

    match = _build_match(rule.get("match"), validator)
    value = _validated_expr(rule.get("value"), validator)
    bind = _build_bind(rule.get("bind"), validator)
    signal = _validated_signal(rule.get("signal", "action_attempted"), match.match_kind)
    injection = _build_injection(rule.get("run_id_injection"))

    return OutcomeRule(
        name=name,
        match=match,
        value=value,
        bind=bind,
        signal=signal,
        run_id_injection=injection,
    )


def _build_match(raw: object, validator: OutcomesPredicateValidator) -> MatchSpec:
    match = _as_mapping(raw, "match")
    kwargs: dict[str, str] = {}
    for key in (*_MATCH_KINDS, "when", "event"):
        candidate = match.get(key)
        if candidate is not None:
            kwargs[key] = _as_str(candidate, f"match.{key}")
    when = kwargs.get("when")
    if when is not None:
        validator.validate(when)
    return MatchSpec(**kwargs)


def _build_bind(raw: object, validator: OutcomesPredicateValidator) -> dict[str, str]:
    if raw is None:
        return {}
    bind_map = _as_mapping(raw, "bind")
    out: dict[str, str] = {}
    for key, expr in bind_map.items():
        expr_str = _as_str(expr, f"bind.{key}")
        validator.validate(expr_str)
        out[key] = expr_str
    return out


def _build_injection(raw: object) -> RunIdInjectionSpec | None:
    if raw is None:
        return None
    block = _as_mapping(raw, "run_id_injection")
    missing = [k for k in _INJECTION_KEYS if k not in block]
    if missing:
        raise OutcomeRuleSchemaError(f"run_id_injection is missing keys: {missing}")
    return RunIdInjectionSpec(
        sdk_call=_as_str(block["sdk_call"], "run_id_injection.sdk_call"),
        inject_into=_as_str(block["inject_into"], "run_id_injection.inject_into"),
        webhook_event=_as_str(block["webhook_event"], "run_id_injection.webhook_event"),
        extract_from=_as_str(block["extract_from"], "run_id_injection.extract_from"),
    )


def _validated_expr(raw: object, validator: OutcomesPredicateValidator) -> str | None:
    if raw is None:
        return None
    expr = _as_str(raw, "value")
    validator.validate(expr)
    return expr


def _validated_signal(raw: object, match_kind: str) -> str:
    declared = _as_str(raw, "signal")
    # The mapper owns the closed vocabulary + the function/http-never-confirmed rule;
    # we surface its rejection as a schema error at author time.
    try:
        SystemSignalClassMapper().map_signal(match_kind=match_kind, declared=declared)
    except ValueError as exc:
        raise OutcomeRuleSchemaError(str(exc)) from exc
    return declared


__all__ = ["load_rules"]
