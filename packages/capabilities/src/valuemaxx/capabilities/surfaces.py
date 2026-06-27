"""Surfaces and modes — the projection vocabulary (§3.2, H5).

A capability declares which :class:`Surface`\\ s it supports (a :class:`~enum.Flag`
mask) and a :class:`Mode`. Surfaces are projections of the registry; NOTIFY is a
required first-class surface (digests), not an afterthought.
"""

from __future__ import annotations

from enum import Flag, StrEnum, auto


class Surface(Flag):
    """The surfaces a capability can be projected onto. NOTIFY is required."""

    API = auto()
    MCP = auto()
    CLI = auto()
    NOTIFY = auto()


class Mode(StrEnum):
    """How a capability is invoked. Exactly four modes (§3.2)."""

    REQUEST_RESPONSE = "request_response"
    STREAMING = "streaming"
    ASYNC_JOB = "async_job"  # -> job_id + status_poll
    WEBHOOK_INBOUND = "webhook_inbound"


__all__ = ["Mode", "Surface"]
