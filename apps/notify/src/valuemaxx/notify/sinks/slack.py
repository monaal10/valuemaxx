"""Slack digest sink — render a :class:`~valuemaxx.notify.models.Digest` payload.

Produces a Slack ``chat.postMessage``-shaped payload (``{"text": ...}``). Pure and
network-free: it renders the aggregate digest text (every metric beside its H7
``minimum_tier`` label) and returns the payload for the caller to deliver.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from valuemaxx.notify.sinks._lines import format_digest_lines

if TYPE_CHECKING:
    from valuemaxx.notify.models import Digest


def render_slack(digest: Digest) -> dict[str, str]:
    """Render ``digest`` into a Slack message payload (``{"text": <lines>}``)."""
    return {"text": "\n".join(format_digest_lines(digest))}


__all__ = ["render_slack"]
