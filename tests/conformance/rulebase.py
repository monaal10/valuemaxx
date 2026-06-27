"""Shared scaffolding for the conformance harness (AGENTS.md §5b).

Every conformance rule is a small module that declares one :class:`Rule`. A rule
carries BOTH a negative fixture (a synthetic violation its check MUST flag) AND a
foundation assertion (what passes against the built foundation today). Foundation
rules go green immediately; the rest are skip-marked with the task id that owns
turning them green — they are never silently xfailed.

The meta-tests in ``tests/conformance/test_meta.py`` enforce, across every rule
module, that the negative fixture is flagged and (for foundation rules) that the
foundation assertion passes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


class RuleKind(Enum):
    """Whether a rule is a static (AST/import) or behavioral (runtime) check."""

    STATIC = "static"
    BEHAVIORAL = "behavioral"


@dataclass(frozen=True, slots=True)
class Rule:
    """One conformance rule: a flagger, a negative fixture, and an owner.

    Attributes:
        name: the rule id (matches the build-plan §3 rule name).
        kind: static or behavioral.
        green_now: True if the foundation already satisfies the rule.
        owner_task: the task id that turns the rule green (for not-yet-green rules).
        flags_violation: returns True iff the given subject violates the rule.
        negative_fixture: a synthetic subject that DOES violate the rule.
        foundation_subject: the real foundation subject the rule must accept
            (only required when ``green_now`` is True).
    """

    name: str
    kind: RuleKind
    green_now: bool
    owner_task: str
    flags_violation: Callable[[object], bool]
    negative_fixture: Callable[[], object]
    foundation_subject: Callable[[], object] | None = None


__all__ = ["Rule", "RuleKind"]
