"""FastAPI + LangChain — valuemaxx one-line init + one outcome (runnable ~30 lines).

valuemaxx.init() installs the cost-capture transport hook; the outcome
(ticket_resolved) is declared in this directory's outcomes.yaml and binds on the
ticket id. Binding tier and signal_class are system-owned — this code never sets
them.
"""

from __future__ import annotations

import valuemaxx
from fastapi import FastAPI
from langchain_anthropic import ChatAnthropic

valuemaxx.init(service="support-bot")  # one line: capture starts here

app = FastAPI()
_model = ChatAnthropic(model="claude-3-5-haiku-latest")


@app.post("/tickets/{ticket_id}/triage")
def triage(ticket_id: str, body: str) -> dict[str, str]:
    """Triage a ticket with the model, then resolve it (the bound outcome)."""
    reply = _model.invoke(f"Triage this support ticket: {body}")
    set_status(ticket_id=ticket_id, status="resolved")  # -> ticket_resolved outcome
    return {"ticket_id": ticket_id, "answer": str(reply.content)}


def set_status(*, ticket_id: str, status: str) -> None:
    """The outcome site declared in outcomes.yaml (function match on status=='resolved')."""
    _ = (ticket_id, status)  # a real app persists the status here
