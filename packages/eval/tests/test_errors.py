"""FOUNDATION: the eval package's typed error hierarchy (one AtmError root)."""

from __future__ import annotations

import pytest
from valuemaxx.core import AtmError
from valuemaxx.eval.errors import (
    BudgetExceededError,
    EvalError,
    GateNotApprovedError,
    GroundTruthUnavailableError,
    JudgeNotValidatedError,
)


@pytest.mark.parametrize(
    "error_cls",
    [
        EvalError,
        BudgetExceededError,
        GateNotApprovedError,
        GroundTruthUnavailableError,
        JudgeNotValidatedError,
    ],
)
def test_every_eval_error_descends_from_atm_error(error_cls: type[AtmError]) -> None:
    """Every eval error shares the one product-wide AtmError root (AGENTS.md §5)."""
    assert issubclass(error_cls, AtmError)


@pytest.mark.parametrize(
    "error_cls",
    [
        BudgetExceededError,
        GateNotApprovedError,
        GroundTruthUnavailableError,
        JudgeNotValidatedError,
    ],
)
def test_specific_errors_descend_from_eval_error(error_cls: type[EvalError]) -> None:
    """The specific failures are catchable as the package base EvalError."""
    assert issubclass(error_cls, EvalError)


def test_errors_carry_their_message() -> None:
    """A raised eval error preserves its human-readable message."""
    with pytest.raises(BudgetExceededError, match="over budget"):
        raise BudgetExceededError("estimate 12.00 is over budget 10.00")
