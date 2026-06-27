"""Tests for the onboarding error hierarchy (FOUNDATION sub-task)."""

from __future__ import annotations

import pytest

from valuemaxx.onboarding.errors import (
    GithubScopeError,
    OnboardingError,
    SecretEncounteredError,
    UnsafePredicateError,
)


def test_all_errors_subclass_onboarding_error() -> None:
    for exc in (SecretEncounteredError, UnsafePredicateError, GithubScopeError):
        assert issubclass(exc, OnboardingError)


def test_onboarding_error_is_an_exception() -> None:
    assert issubclass(OnboardingError, Exception)


def test_errors_are_raisable_and_carry_message() -> None:
    with pytest.raises(SecretEncounteredError, match="leak"):
        raise SecretEncounteredError("would leak a key")
    with pytest.raises(UnsafePredicateError):
        raise UnsafePredicateError("eval is forbidden")
    with pytest.raises(GithubScopeError):
        raise GithubScopeError("scope too broad")
