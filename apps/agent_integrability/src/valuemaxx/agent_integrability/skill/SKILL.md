---
name: valuemaxx-integration
description: >-
  Wire valuemaxx (AI margin intelligence — cost-per-outcome with confidence) into a
  codebase. Use when adding cost capture, defining outcomes, or measuring
  cost-per-outcome for an AI agent app. Scans the repo, proposes outcomes, validates
  them, and hands off a reviewable diff — never auto-applies a rule.
---

# valuemaxx integration Skill

valuemaxx measures **cost-per-outcome with confidence**. Surfaces (API/MCP/CLI/notify)
are thin projections of one capability registry; everything below is driven through
those capabilities. The flow is **scan → propose → wire → validate → hand-off as a
diff**.

## Honesty invariants (do NOT violate)

The three axes are **system-owned** — never set or guess them:

- **Binding tier** (`exact | deterministic | candidate | likely`) is system-owned. An
  inferred match is never `exact`. `candidate`/`likely` are advisory, never
  billing-grade.
- **signal_class** (`action_attempted | outcome_confirmed | outcome_retracted`) is
  **system-mapped** from the outcome source. A successful tool call is
  `action_attempted` unless the result is authoritative.
- **Cost provenance** is system-owned; an estimate is never rendered as billed.

Every rollup carries `minimum_tier` + `confidence_distribution` — never collapse them.

## Steps

> **Two approval gates.** This edits the host's production LLM call path. Stop and wait
> for a human before writing capture wiring (step 3) and before writing `outcomes.yaml`
> (step 4). Do not edit any file before the first approval. If the scope grows while you
> work — a one-file change reaching five files, typically from threading a handle through
> intermediate layers — stop and re-ask; it is no longer what they approved. Never run
> destructive git commands on their tree, and never weaken a host safety setting
> (lockfile policy, supply-chain minimum-release-age, a CI gate) to unblock yourself.

1. **Scan** the codebase for run boundaries (where `valuemaxx.init()` goes) and
   candidate outcome sites (status setters, ORM saves, outbound Stripe/CRM/email
   calls, webhook handlers). Use the `scan_codebase` capability.
2. **Propose** outcomes with `propose_onboarding_diff` (or draft a single rule with
   `scaffold_outcome_rule`). Every proposal is an **UNCONFIRMED candidate**.
3. **Wire** the SDK init at the app entrypoint — **after** presenting the exact file list
   (and which model-call entry points it does and does not cover) and getting an explicit
   go-ahead. Offer the smallest useful scope first: usually the host's one LLM wrapper,
   one file. Then validate the snippet with
   `validate_init`. `init()` is **not** zero-argument — it takes `tenant_id`,
   `ingest_key`, and `endpoint` (there is no default hosted endpoint; the user runs the
   backend). Pick the capture path from the host's dependency manifest:
   - raw `openai` / `@anthropic-ai/sdk` client instances → pass them via `clients`;
   - **Vercel AI SDK (`ai`/`@ai-sdk/*`) with no raw provider clients → `clients` does
     not apply.** Use the tracer `init()` returns and pass
     `experimental_telemetry: {isEnabled: true, tracer}` to `generateText`/`streamText`
     — ideally threaded once through the host's own LLM wrapper module;
   - LangChain/LlamaIndex/custom HTTP → tracer path, or OTLP direct.

   Runtime: Node ≥ 20 with `node:async_hooks` + `node:crypto` (on Cloudflare
   Workers/workerd that means `nodejs_compat` must be enabled).
4. **Validate** the `outcomes.yaml` with `validate_outcome_rule` (the safe-predicate
   allowlist — no `eval`, no dunder access).
5. **Suggest** an attribution rule with `suggest_attribution_rule` — it returns an
   UNCONFIRMED candidate. Do **not** hand-write or auto-apply a rule.
6. **Hand off** the change as a reviewable diff (hunks only). A human confirms; the
   system never auto-applies.

See the generated `llms.txt` for the full capability list, and `examples/` for
per-framework starting points (fastapi+langchain, openai, anthropic). Each example
ships a runnable snippet plus a validating `outcomes.yaml`.
