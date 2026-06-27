"""OUT-B: the system-owned SignalClassMapper (function/http never confirmed)."""

from __future__ import annotations

import pytest
from valuemaxx.core import SignalClass, SignalClassMapper
from valuemaxx.outcomes.signal import SystemSignalClassMapper


def test_mapper_satisfies_core_protocol() -> None:
    """SystemSignalClassMapper structurally satisfies the core Protocol."""
    assert isinstance(SystemSignalClassMapper(), SignalClassMapper)


@pytest.mark.parametrize("match_kind", ["function", "http"])
def test_function_and_http_can_never_yield_confirmed(match_kind: str) -> None:
    """A function/HTTP match is action_attempted even if the rule declared confirmed.

    The signal class is system-owned: a 200/successful call is not business success.
    """
    mapper = SystemSignalClassMapper()
    result = mapper.map_signal(match_kind=match_kind, declared=SignalClass.OUTCOME_CONFIRMED.value)
    assert result == SignalClass.ACTION_ATTEMPTED.value


@pytest.mark.parametrize("match_kind", ["webhook", "status_transition", "orm_save"])
def test_authoritative_kinds_honor_declared_confirmed(match_kind: str) -> None:
    """Authoritative match kinds (webhook/status/orm) may carry confirmed when declared."""
    mapper = SystemSignalClassMapper()
    result = mapper.map_signal(match_kind=match_kind, declared=SignalClass.OUTCOME_CONFIRMED.value)
    assert result == SignalClass.OUTCOME_CONFIRMED.value


def test_declared_attempted_is_never_promoted() -> None:
    """A declared action_attempted is never silently promoted to confirmed."""
    mapper = SystemSignalClassMapper()
    for kind in ("function", "http", "webhook", "status_transition", "orm_save"):
        result = mapper.map_signal(match_kind=kind, declared=SignalClass.ACTION_ATTEMPTED.value)
        assert result == SignalClass.ACTION_ATTEMPTED.value


def test_retracted_is_not_an_emit_time_declaration() -> None:
    """A rule cannot declare outcome_retracted at emit time (retraction is a later flip)."""
    mapper = SystemSignalClassMapper()
    with pytest.raises(ValueError, match="retracted"):
        mapper.map_signal(match_kind="webhook", declared=SignalClass.OUTCOME_RETRACTED.value)


def test_unknown_declared_value_rejected() -> None:
    """An unknown declared signal string is rejected (closed vocabulary)."""
    mapper = SystemSignalClassMapper()
    with pytest.raises(ValueError, match="declared"):
        mapper.map_signal(match_kind="webhook", declared="totally_made_up")


def test_unknown_match_kind_rejected() -> None:
    """An unknown match kind is rejected (closed vocabulary)."""
    mapper = SystemSignalClassMapper()
    with pytest.raises(ValueError, match="match_kind"):
        mapper.map_signal(match_kind="telepathy", declared=SignalClass.ACTION_ATTEMPTED.value)
