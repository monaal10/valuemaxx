---
name: integrate-valuemaxx
description: Use when a user wants to integrate valuemaxx (AI agent cost-per-outcome tracking) into their codebase. Scans the repo, proposes outcomes, wires capture, and configures attribution — all reviewable.
---

# Integrating valuemaxx into a codebase

valuemaxx captures the **correct** cost of every LLM call, binds it to the **business outcome** each agent run produced, and tells you whether a cheaper model would hold that outcome. This skill drives the integration **for** the user: you scan their code, propose what to track, write the wiring, and hand back a reviewable diff. The human's only job is to approve.

> **Golden rule:** propose, never assume. Everything you write is reviewable. Never invent an outcome the user didn't confirm. Never weaken the honesty labels.

## The integration, step by step

### 1. Install + capture (zero outcome data yet)
Add the SDK and one line. This alone gives total + per-model + per-agent cost.

```bash
pip install valuemaxx        # Python
npm install valuemaxx        # TypeScript/JS
```
```python
import valuemaxx
valuemaxx.init()             # zero-code cost capture; off the hot path; never throws into the app
```
Run `valuemaxx init` to let the CLI detect the framework (FastAPI/Django/LangChain/Next/Express) and inject `init()` in the right place as a reviewable change. It also writes a short `AGENTS.md` snippet into the user's repo so future agents know valuemaxx is present.

### 2. Discover the outcomes (you do this by reading their code)
Scan the codebase for:
- **where the agent runs** — the LLM call sites / run boundaries (so a `valuemaxx.run(...)` context can wrap them).
- **candidate outcome points** — functions/writes that represent a business result: `*_status` setters, `mark_*`/`resolve`/`close`/`approve`, ORM saves that flip a state field, outbound calls to Stripe/CRM/calendar/email, and webhook handlers.
- **durable entity IDs in scope at the run** — `customer_id`, `application_id`, `conversation_id`, email — these let *delayed* outcomes bind back.
- **external writes** where a `run_id` can be round-tripped (Stripe `metadata`, a ticket custom field) so a later webhook echoes it back → deterministic binding.

### 3. Propose (the human's only touch point)
Present a short summary: *"I found these N outcomes, each run carries this entity ID, these can be bound deterministically and these will be candidate/likely confidence."* Let the human edit/confirm. Then write the config.

### 4. Generate the wiring (hybrid — you choose per outcome)
- **in-process outcome** (a function/ORM-write in their app) → a declarative rule in `valuemaxx.outcomes.yaml`. The SDK instruments the named function at `init()`; no per-call-site edits.
- **delayed / external outcome** (a webhook days later) → an explicit captured line in the webhook handler **plus** a `run_id_injection` block so the run_id round-trips and the outcome binds deterministically.
- **entity-id capture** → one `valuemaxx.run(customer_id=...)`-style line at the run entry, using IDs already in scope.

### 5. Validate, then hand off
Call the valuemaxx MCP `validate_*` tools to confirm each rule produces a well-formed, bindable outcome; optionally dry-run against recent traffic to preview `cost-per-<outcome>`. Then deliver everything as a **reviewable diff / PR** — explicit, version-controlled, nothing silent.

## What you must NOT do
- Don't exfiltrate raw source — emit the proposed config/diff, not the codebase.
- Don't ever echo a secret you encountered while scanning into the diff or logs.
- Don't mark a fuzzy (email/time-window) match as high-confidence — the system owns the confidence label; you only declare the rule.
- Don't change how the human's app works — valuemaxx reads what's already there.

## The outcome rule shape (what you write into `valuemaxx.outcomes.yaml`)

```yaml
outcomes:
  - name: loan_funded
    match: { function: "myapp.loans.update_loan_status", when: "args.status == 'funded'" }
    value: "args.amount"
    bind:  { entity_key: "args.application_id" }
    signal: outcome_confirmed

  - name: payment_succeeded          # delayed/external — round-trip the run_id
    match: { webhook: stripe, event: "payment_intent.succeeded" }
    run_id_injection:
      sdk_call:    "stripe.PaymentIntent.create"
      inject_into: "metadata.run_id"
      webhook_event: "payment_intent.succeeded"
      extract_from:  "data.object.metadata.run_id"
    value: "data.object.amount"
    signal: outcome_confirmed
```
