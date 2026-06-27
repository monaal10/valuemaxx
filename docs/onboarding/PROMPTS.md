# valuemaxx onboarding prompts

Ready-to-use prompts for driving valuemaxx integration with an AI coding agent (Claude Code, Cursor, etc.). Paste the relevant one to your agent; it follows the `integrate-valuemaxx` skill (`SKILL.md`).

---

## Prompt 1 — Full guided integration (recommended)

> Integrate **valuemaxx** into this codebase so I can see what each AI agent costs and what it earns, per outcome.
>
> 1. Install the SDK (`pip install valuemaxx` / `npm install valuemaxx`) and add `valuemaxx.init()` at app startup — run `valuemaxx init` to detect my framework and place it correctly.
> 2. Scan the repo and find: where my agent(s) run, the points where a **business outcome** is recorded (a resolution / deal / payment / completed task — functions that set a status, ORM saves, Stripe/CRM/calendar calls, webhook handlers), and the durable entity IDs in scope (customer_id, conversation_id, email).
> 3. **Show me a list** of the candidate outcomes + the entity ID each run carries, and tell me which can be bound deterministically vs which will be lower-confidence. Wait for my confirmation.
> 4. Write the `valuemaxx.outcomes.yaml` config (and, for delayed/webhook outcomes, the run_id round-trip injection), validate it with the valuemaxx MCP `validate_*` tools, and give me a single reviewable diff/PR.
>
> Do not change how my app works, do not echo any secrets, and never mark a fuzzy match as high-confidence.

---

## Prompt 2 — Just capture cost (no outcomes yet)

> Add **valuemaxx** cost capture to this project: install the SDK, run `valuemaxx init` to wire `valuemaxx.init()` into my framework, and confirm it's capturing LLM cost off the hot path. Don't set up outcomes yet — I just want to see my spend by model and by agent first.

---

## Prompt 3 — Add one specific outcome

> I want valuemaxx to track **"<OUTCOME, e.g. a booked demo>"** as an outcome. Find where that happens in my code (or which webhook signals it), propose the `valuemaxx.outcomes.yaml` rule — including how to bind it back to the agent run that caused it — show me the diff, and validate it. Use the `suggest_attribution_rule` MCP tool if you're unsure which code site maps to my description.

---

## Prompt 4 — Set up the right-sizing / eval check

> Set up valuemaxx's eval-backed model recommendation for my **"<AGENT/TASK>"**. It already has my real outcomes; enable the eval with my provider keys (these spend my tokens, so show me the per-candidate cost estimate and ask before each run), prune to a few candidate models, and produce a recommendation report on whether a cheaper/faster model holds my outcome — but never switch automatically.

---

## What to expect

- You only ever **review** — the agent writes the wiring and hands you a diff.
- Every number valuemaxx shows is **honesty-labeled**: cost provenance (measured/estimated/reconciled), binding tier (exact→likely), outcome signal (attempted/confirmed/retracted).
- Nothing about how your app runs changes; valuemaxx reads what's already there.
- The SDK never throws into your app and adds <1ms; if it can't reach the backend it drops telemetry (counted), never blocks.
