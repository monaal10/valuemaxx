"""tenant_scoping — every repo query path takes tenant_id first (foundation-green shape).

There is no API to query a store without a tenant scope. ``flags_violation``
takes a repository-like class and returns True if ANY abstract method's first
parameter (after self) is not ``tenant_id``. The negative fixture is a synthetic
repo with an untenanted method; the foundation subject is a real core repo ABC.
"""

from __future__ import annotations

import inspect
from abc import ABC, abstractmethod

from valuemaxx.core.repositories import RunRepository

from tests.conformance.rulebase import Rule, RuleKind


def _first_param_is_tenant(cls: type, method_name: str) -> bool:
    func = getattr(cls, method_name)
    params = [p for p in inspect.signature(func).parameters if p != "self"]
    return bool(params) and params[0] == "tenant_id"


def _flags(subject: object) -> bool:
    assert isinstance(subject, type)
    abstract: frozenset[str] = getattr(subject, "__abstractmethods__", frozenset())
    method_names = abstract or {
        n for n, _ in inspect.getmembers(subject, predicate=inspect.isfunction)
    }
    return any(not _first_param_is_tenant(subject, name) for name in method_names)


class _UntenantedRepo(ABC):
    @abstractmethod
    def get(self, run_id: str) -> object:  # missing tenant_id first -> violation
        ...


def _negative_fixture() -> object:
    return _UntenantedRepo


def _foundation_subject() -> object:
    return RunRepository


RULE = Rule(
    name="tenant_scoping",
    kind=RuleKind.STATIC,
    green_now=True,
    owner_task="foundation",  # final owner STORE; foundation ABCs already tenant-first
    flags_violation=_flags,
    negative_fixture=_negative_fixture,
    foundation_subject=_foundation_subject,
)
