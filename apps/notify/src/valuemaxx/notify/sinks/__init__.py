"""Digest sinks — render an aggregate :class:`~valuemaxx.notify.models.Digest`.

Each sink renders a digest into a delivery payload (Slack message / email body). A
sink never invents raw content; it shows only the aggregate metric value beside its
H7 ``minimum_tier`` label, so a number never renders without its confidence.
"""

from __future__ import annotations

__all__: list[str] = []
