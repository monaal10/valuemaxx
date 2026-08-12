# valuemaxx onboarding prompts

Ready-to-use prompts for driving valuemaxx integration with an AI coding agent (Claude Code, Cursor, etc.). Paste the relevant one to your agent; it follows the `integrate-valuemaxx` skill (`SKILL.md`).

> These lead with the **gateway**, which is the front door: a base-URL swap and a few headers, with none of our code in your request path. The SDK is a compat path for providers the gateway cannot proxy (Bedrock, Vertex) or a house OTel collector — not the way in. If a prompt tells your agent to `pip install valuemaxx` and call `init()` first, it is out of date.

---

## Prompt 1 — Full guided integration (recommended)

> Integrate **valuemaxx** into this codebase so I can see what each AI agent costs and what it earns, per outcome.
>
> 1. Read `llms.txt` and `docs/onboarding/SKILL.md` first. Use the **gateway** path: point my LLM client's base URL at the gateway and set the `x-vmx-*` headers. Do not install an SDK and do not add an `init()` call unless my provider cannot be proxied.
> 2. **Before editing anything**, ask me what one "unit of work" is — the thing I want a cost *per* — and which durable id of mine identifies it. Nothing in my code answers this and getting it wrong quietly distorts every number.
> 3. Scan the repo and find where a **business outcome** becomes true (a status flip, an ORM save, a Stripe/CRM/calendar call, a webhook handler), plus the durable ids in scope. Show me the candidates and which can bind deterministically versus which will be lower-confidence. Wait for my confirmation.
> 4. Wire it: base URL plus headers for capture, and one `POST /v1/outcome` call where each confirmed outcome happens. Give me a single reviewable diff.
>
> Tell me explicitly if my app streams from OpenAI, if the same work is known by different ids at different stages, or if an outcome can land more than 35 days after the work — each needs a specific handling and silently produces wrong numbers otherwise.
>
> Do not change how my app works, do not echo any secrets, and never mark a fuzzy match as high-confidence.

---

## Prompt 2 — Just capture cost (no outcomes yet)

> Add **valuemaxx** cost capture to this project using the gateway: point my LLM client's base URL at it, set `x-vmx-key` and `x-vmx-agent`, and use my own durable business id as `x-vmx-run-id` so calls group into real units. If I stream from OpenAI, also set `stream_options={"include_usage": true}` and tell me why. Don't set up outcomes yet — I want to see spend by model and by agent first.

---

## Prompt 3 — Add one specific outcome

> I want valuemaxx to track **"&lt;OUTCOME, e.g. a booked demo&gt;"** as an outcome. Find where that happens in my code (or which webhook signals it) and add the `POST /v1/outcome` call there, carrying the same durable id my LLM calls use so it binds at `exact`. Set `identifier` for idempotency if the path can retry. Show me the diff. If the outcome arrives in a different process or days later, say so and explain how it still joins.

---

## Prompt 4 — The id changes partway through

> In this codebase, work starts under one id and the outcome arrives under another — **&lt;e.g. an anonymous session that becomes a known lead&gt;**. Show me where each id is available, keep sending whichever is in scope at the time, and add the `POST /v1/alias` call at the moment the link becomes known. Explain what spend would be orphaned without it.

---

## Prompt 5 — Set up the right-sizing / eval check

> Set up valuemaxx's eval-backed model recommendation for my **"&lt;AGENT/TASK&gt;"**. It already has my real outcomes; enable the eval with my provider keys (these spend my tokens, so show me the per-candidate cost estimate and ask before each run), prune to a few candidate models, and produce a recommendation report on whether a cheaper/faster model holds my outcome — but never switch automatically.

---

## What to expect

- You only ever **review** — the agent writes the wiring and hands you a diff.
- Every number valuemaxx shows is **honesty-labeled**: cost provenance (measured/estimated/reconciled), binding tier (exact→likely), outcome signal (attempted/confirmed/retracted), and whether the link was observed or inferred.
- Nothing of ours runs inside your request path. A gateway failure falls back to a plain passthrough: losing a span is acceptable, losing your request is not.
- Recording an outcome is a plain HTTP call you own — give it a timeout and let it fail quietly. It must never break a working feature.
