"""Typed errors for the onboarding agent (FOUNDATION).

Every onboarding failure is an :class:`OnboardingError` subclass so callers can
catch the package's errors precisely (AGENTS.md §5: no bare exceptions). The three
specialised errors map to the agent's three safety boundaries:

* :class:`SecretEncounteredError` — a secret-shaped token reached a field/diff/log
  that must never carry one (the ``no_secret_logging`` guardrail).
* :class:`UnsafePredicateError` — a proposed ``when`` predicate failed the AST
  allowlist (the ``no_eval_in_predicate`` guardrail).
* :class:`GithubScopeError` — a GitHub-App operation requested a scope beyond the
  read-only / PR-write envelope (H12).
"""

from __future__ import annotations


class OnboardingError(Exception):
    """Base class for every error raised by the onboarding agent."""


class SecretEncounteredError(OnboardingError):
    """A secret-shaped token reached an output that must never carry a secret."""


class UnsafePredicateError(OnboardingError):
    """A proposed predicate uses a construct outside the safe AST allowlist."""


class GithubScopeError(OnboardingError):
    """A GitHub-App operation requested a scope beyond ``contents:read``/``pull_requests:write``."""


__all__ = [
    "GithubScopeError",
    "OnboardingError",
    "SecretEncounteredError",
    "UnsafePredicateError",
]
