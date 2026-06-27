"""OpenAI — valuemaxx one-line init + one outcome (runnable ~30 lines).

valuemaxx.init() installs the cost-capture transport hook for the OpenAI client. The
outcome (payment_succeeded) is declared in this directory's outcomes.yaml and binds
via a Stripe webhook with run_id injection. signal_class is system-mapped; this code
never sets it.
"""

from __future__ import annotations

import stripe
import valuemaxx
from openai import OpenAI

valuemaxx.init(service="checkout-agent")  # one line: capture starts here

_client = OpenAI()


def recommend_and_charge(run_id: str, prompt: str, amount_cents: int) -> str:
    """Get a recommendation, then create a charge tagged with the run_id."""
    completion = _client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )
    # run_id_injection: tag the charge so the webhook outcome binds deterministically.
    stripe.PaymentIntent.create(
        amount=amount_cents,
        currency="usd",
        metadata={"run_id": run_id},  # -> payment_succeeded outcome on webhook
    )
    return completion.choices[0].message.content or ""
