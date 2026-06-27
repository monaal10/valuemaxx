"""F0-CAPS: Surface (incl NOTIFY) + Mode (exactly four)."""

from __future__ import annotations

from enum import Flag, StrEnum

from valuemaxx.capabilities.surfaces import Mode, Surface


def test_surface_set_is_exactly_four() -> None:
    """T-CAP-1: Surface includes API, MCP, CLI, NOTIFY — exactly these four."""
    names = {s.name for s in Surface}
    assert names == {"API", "MCP", "CLI", "NOTIFY"}


def test_surface_is_a_flag() -> None:
    """Surface is a Flag so a capability can declare a mask of surfaces."""
    assert issubclass(Surface, Flag)
    combined = Surface.API | Surface.MCP
    assert Surface.API in combined
    assert Surface.CLI not in combined


def test_notify_is_present() -> None:
    """NOTIFY is required (digests are a first-class surface)."""
    assert Surface.NOTIFY in Surface


def test_mode_has_exactly_four_values() -> None:
    """T-CAP-2: Mode = request_response | streaming | async_job | webhook_inbound."""
    assert {m.value for m in Mode} == {
        "request_response",
        "streaming",
        "async_job",
        "webhook_inbound",
    }
    assert issubclass(Mode, StrEnum)
