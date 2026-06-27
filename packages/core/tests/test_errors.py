"""F0-CORE-1a: the typed error hierarchy (no bare exceptions downstream)."""

from __future__ import annotations

import pytest
from atm_core import errors


def test_all_errors_subclass_atm_error() -> None:
    """Every domain error subclasses AtmError so callers can catch one root."""
    for err_cls in (
        errors.TenantScopeError,
        errors.ProvenanceWarning,
        errors.HonestyInvariantError,
        errors.CaptureError,
        errors.BindingAmbiguityError,
    ):
        assert issubclass(err_cls, errors.AtmError)


def test_atm_error_is_an_exception() -> None:
    assert issubclass(errors.AtmError, Exception)


def test_errors_are_raisable_and_carry_message() -> None:
    """An AtmError subclass is catchable as AtmError and carries its message."""
    with pytest.raises(errors.AtmError, match="estimate rendered as billed"):
        raise errors.HonestyInvariantError("estimate rendered as billed")


def test_all_errors_exported() -> None:
    expected = {
        "AtmError",
        "TenantScopeError",
        "ProvenanceWarning",
        "HonestyInvariantError",
        "CaptureError",
        "BindingAmbiguityError",
    }
    assert expected <= set(errors.__all__)
