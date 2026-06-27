"""Anthropic — valuemaxx one-line init + one outcome (runnable ~30 lines).

valuemaxx.init() installs the cost-capture transport hook for the Anthropic client.
The outcome (lead_qualified) is declared in this directory's outcomes.yaml and binds
on an ORM save of the Lead. Binding tier is system-owned; this code never sets it.
"""

from __future__ import annotations

import valuemaxx
from anthropic import Anthropic

valuemaxx.init(service="sdr-agent")  # one line: capture starts here

_client = Anthropic()


def qualify_lead(lead_id: str, notes: str) -> str:
    """Ask the model to qualify a lead, then persist the qualification (the outcome)."""
    message = _client.messages.create(
        model="claude-3-5-haiku-latest",
        max_tokens=256,
        messages=[{"role": "user", "content": f"Qualify this lead: {notes}"}],
    )
    save_lead(lead_id=lead_id, stage="qualified")  # -> lead_qualified outcome
    return message.content[0].text if message.content else ""


def save_lead(*, lead_id: str, stage: str) -> None:
    """The outcome site declared in outcomes.yaml (orm_save match on stage=='qualified')."""
    _ = (lead_id, stage)  # a real app persists the Lead here
