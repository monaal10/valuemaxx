---
name: integrate-valuemaxx
description: Use when a user wants to integrate valuemaxx (AI agent cost-per-outcome tracking) into their codebase. Scans the repo, proposes outcomes, wires capture, and configures attribution — all reviewable.
---

# Integrating valuemaxx into a codebase

valuemaxx captures the **correct** cost of every LLM call, binds it to the **business outcome** each agent run produced, and tells you whether a cheaper model would hold that outcome. This skill drives the integration **for** the user: you scan their code, propose what to track, propose the wiring, and — once they approve — write it as a reviewable diff.

> **Golden rule:** propose, never assume. Everything you write is reviewable. Never invent an outcome the user didn't confirm. Never weaken the honesty labels.

> **STOP-AND-ASK, THREE TIMES.** This integration has **three** approval gates, and you must
> stop at every one — do not edit a single file before the human answers:
>
> 1. **Before writing capture wiring** (step 1c) — you present the exact file list and
>    the reason for each; they approve the scope.
> 2. **Before wiring a run boundary** (step 2) — they define what one "unit of work" IS.
>    No scan can infer this, and getting it wrong silently distorts every cost number.
> 3. **Before writing `outcomes.yaml`** (step 4) — they confirm which outcomes are real.
>
> These are someone else's production LLM call path. An agent that "just wires it up" has
> made an unreviewed change to how every model call in their app behaves.

> **You should not need to read valuemaxx's own source to do this.** This skill plus
> [`llms.txt`](../../llms.txt) is the contract: install, capture path, runtime requirements,
> backend, and the outcome scan are all specified below. If you find yourself cloning the
> valuemaxx repo to answer a question about *how to integrate it*, that is a documentation
> bug — tell the user what was missing so it can be fixed.

## The integration, step by step

### 1. Install + capture (zero outcome data yet)
Add the SDK and one line. This alone gives total + per-model + per-agent cost.

```bash
pip install valuemaxx        # Python
npm install valuemaxx        # TypeScript/JS
```

**`init()` is not zero-argument.** It requires `tenant_id`, `ingest_key`, and `endpoint` —
there is no default hosted endpoint, so decide where the backend runs (step 1c) before wiring.

```python
import valuemaxx.sdk as valuemaxx
vmx = valuemaxx.init(tenant_id=UUID(...), ingest_key="dev", endpoint="http://127.0.0.1:8000")
```

**1a. Pick the capture path — check the host's dependency manifest FIRST.** This is the fork
agents most often get wrong, and picking wrong means capturing nothing:

| The host uses | Capture path |
|---|---|
| Raw `openai` / `@anthropic-ai/sdk` client instances | Pass them to `init({clients: [...]})` |
| **Vercel AI SDK (`ai`, `@ai-sdk/*`) with no raw provider clients** | **`clients` does NOT apply.** Use the tracer (below) |
| LangChain / LlamaIndex / custom HTTP | Tracer path, or OTLP direct |

`clients` wraps the two provider SDKs *by instance*. An AI-SDK-only codebase has no such
instance to hand it, so the tracer is the ONLY route. The complete TypeScript form:

```ts
import { init, run } from "valuemaxx";   // single entrypoint; there is no subpath export

const vmx = init({
  tenantId: env.VALUEMAXX_TENANT_ID,     // a plain string (NOT a UUID object, unlike Python)
  ingestKey: env.VALUEMAXX_INGEST_KEY,   // secret — route it through your secret store
  endpoint: env.VALUEMAXX_ENDPOINT,      // http(s) URL; no default exists
});

// `InitResult.tracer` is `Tracer | undefined` — it is undefined when the exporter/provider
// failed to start (fail-open). Guard it; do NOT destructure it as if it were always defined.
await generateText({
  model,
  prompt,
  ...(vmx.tracer ? { experimental_telemetry: { isEnabled: true, tracer: vmx.tracer } } : {}),
});

// Bind a run so every call inside shares one run id (this is what earns `exact` tier):
await run("checkout-agent-42", async () => { /* ... model calls ... */ });
```

Spreading (rather than passing `tracer: undefined`) is what keeps this compiling under
`exactOptionalPropertyTypes`. `forceFlush`/`shutdown` are **methods** on `InitResult` — call
them as `vmx.forceFlush()` rather than destructuring, so they stay bound to their result.

**Typing the tracer in your own signatures?** The `Tracer` type comes from
`@opentelemetry/api`. valuemaxx depends on it, but it may not be hoisted where your host can
`import type` it — add it as a direct dev dependency, or derive it structurally without a new
dep: `type VmxTracer = NonNullable<ReturnType<typeof init>["tracer"]>`.

**Making it inert.** `init()`'s *config validation* is the one thing that throws
(`InitConfigError`) — a missing or non-http endpoint is a call-site programming error, not a
silent degrade. So "inert" means **not calling `init()` at all**:

```ts
const vmx = env.VALUEMAXX_ENDPOINT ? init({ ... }) : undefined;
// then spread as above on `vmx?.tracer`
```

Everything *after* config validation is fail-open: instrumentation errors are caught, logged,
and surfaced on `InitResult.warnings` — they never propagate into your call path.

**Call `init()` once per process/isolate, not per request.** It stands up an OTLP exporter and
a batch span processor; calling it per request rebuilds them and leaks. Memoize it at module
scope (in a Worker, that is once per isolate).

**Find every model-construction path before you edit.** "Thread it once" assumes a single
funnel; real codebases often have a primary wrapper plus one or more bypasses that build a
model directly and call `streamText` themselves. Grep for every `generateText`/`streamText`
call site, not just the wrapper — a bypass you miss captures *nothing*, silently. If the host
already has its own tracing wrapper, the bypasses are usually whatever that wrapper had to
special-case.

**Short-lived runtimes (Workers, Lambda).** There is no process exit to flush on. Call
`vmx.forceFlush()` before the isolate can be frozen (e.g. inside `ctx.waitUntil(...)`), or
spans may be dropped. On a **streaming** response the spans are emitted as the stream is
consumed, i.e. *after* the handler returns — flush when the stream settles, not at return.

**Distributed hosts (multi-service, workflow engines, queues).** `run()` binds the run id in
**AsyncLocalStorage**, so it covers one in-process async scope and nothing more. It does NOT
survive an RPC hop, a queue, or a workflow step resumed from persisted state days later. That
matters because the run id is what earns the `exact` binding tier — lose it and everything
downstream degrades to `candidate`/`likely`, which is never billing-grade.

Two carries close the gap, and both are declared at `init()` — you wire nothing per call:

- **Live service→service hop** — `baggage_targets` wraps your outbound HTTP method so the
  active run id rides the W3C `baggage` header; the receiving service parses it back and the
  cascade still binds `exact`.
- **Delayed / out-of-process outcome** — `run_id_injection` stamps the run id into an
  outbound object (e.g. Stripe `metadata`) whose later webhook echoes it back, binding
  `deterministic`.

Choosing the run boundary is a judgment call the tool cannot make for you — it is step 2,
and it is a hard gate. Do not guess it here.

**1b. Runtime.** Node >= 20. Needs `node:async_hooks` (AsyncLocalStorage — the in-process
run-id carry) and `node:crypto`. On Cloudflare Workers/workerd, `nodejs_compat` must be
enabled; with it, capture works. On Deno/Bun, verify `run()` actually binds before relying
on the `exact` tier.

**1c. The backend.** Cost spans go to a backend the user runs — `docker run -p 8000:8000
valuemaxx-backend`, or `valuemaxx up` if they have Python. If they haven't decided where it
runs, wire capture to be INERT unless the endpoint env var is set. Never invent an endpoint
and never point telemetry at a host the user didn't choose.

**1d. Scaffolding.** `valuemaxx init` (Python CLI only) detects a Python framework and emits
a reviewable diff — it looks for a Python entrypoint (`main.py`/`manage.py`) and cannot
scaffold a TS/JS repo. The npm CLI ships `onboard` only; wire `init()` by hand there.

**1e. GATE — get approval on the file list BEFORE you edit anything.**

You now know enough to say exactly what you would change. Say it, and stop. Present:

| | |
|---|---|
| **Files** | Every file you'd touch, with one line on why each |
| **Entry points** | Which model-call paths this covers — and which it does **not** |
| **Blast radius** | That this sits on their production LLM call path, and that it's inert until the endpoint env var is set |
| **Unknowns** | The run-boundary choice, an unreachable platform-native call, anything you had to assume |

Then ask which scope they want, and wait. Offer the smallest useful version first —
**one wrapper, one file** — because that is usually the right amount:

- **Chokepoint only** — the host's single LLM wrapper. Small, reviewable, covers most calls.
- **Chokepoint + bypasses** — also threads the secondary entry points. Complete coverage,
  but threading a handle from where `env` lives to where the call happens can cross several
  files; if it does, that is exactly the kind of growth to flag rather than absorb.
- **Nothing yet** — they wire it themselves from your proposal.

**If the scope grows while you work, stop and re-ask.** A one-file change that turns into a
five-file change is no longer the thing they approved. Threading a new parameter through
intermediate layers is the usual cause: each hop looks trivial, and the total is a
signature change across the codebase. Say what you found, and let them re-decide.

Do not start with a proposal and then edit anyway because the change "seemed small". The
approval is the gate, not a formality you narrate past.

### 2. GATE — agree what a "unit of work" is, before wiring anything

**This is the question everything else depends on, and nothing in the code answers it.**
Cost is only meaningful per unit — *per alt built*, *per ticket resolved*, *per document
processed*. A repo scan can find every LLM call; it cannot know which calls belong to the
same unit. Only the user knows, and they usually have never been asked.

Get it wrong and every downstream number is quietly wrong: ten calls that were really one
unit read as ten cheap units, or one expensive one. Nothing errors. So ask.

**Open with what you found, not a blank prompt.** The scan already gives you call sites
and in-scope ids — make the user CORRECT you rather than author from nothing:

> I found LLM calls in 5 places under `src/pipeline/` — `extract`, `classify`,
> `enrich`, `summarise`, and 3 more in `render`. They look like stages of one
> bigger operation.
>
> When you say "this cost too much" — what is *this*?
>   a) one whole pipeline run (all ~8 calls together)
>   b) each stage separately
>   c) something spanning several runs — per customer, per document
>   d) something else — describe it

Then resolve the **run id**: what value is identical across every call in one unit, and
different between units? Look for one that already exists rather than inventing one:

| Shape of codebase | Usually the right id |
|---|---|
| Workflow / job engine | the workflow-instance or job id (stable across steps AND workers) |
| HTTP service | the request id, or a trace id if they already run OTel |
| Queue consumer | the message id |
| Agent framework | the invocation/session id the framework already assigns |
| Script / batch | generate one per invocation |

Ask directly: *"is there an id already in scope at every one of these call sites?"* An
existing id beats a new one — it survives process and service boundaries, which an
in-process scope does not.

Then resolve **entity keys** — the durable business ids the unit is about (`alt_id`,
`ticket_id`, `loan_id`). These are what let a unit span SEVERAL runs later, and they
**cannot be backfilled**: history recorded without them stays unattributable. Say that
plainly, because it is the one decision with a deadline.

**Ground the choice in a number before accepting it.** Once capture has run briefly,
show what the boundary implies — *"with this boundary your last 20 runs averaged
$0.02 each; a stage boundary would say $0.0025"* — and let them confirm the one that
matches their intuition. A boundary nobody has sanity-checked is a guess with a
dollar sign in front of it.

Write the answer to `valuemaxx.yaml` so it is reviewable, diffable and re-runnable:

```yaml
unit_of_work:
  name: alt                       # what one unit is called, in their words
  run_id_source: ctx.workflowInstanceId   # the value identical across the unit
  entity_keys: [alt_id]           # durable ids the unit is about (optional)
```

and wire it at the run boundary — one call, not per call site:

```ts
await run(ctx.workflowInstanceId, { agentName: "build-alt", entityKeys: { alt_id } },
  async () => { /* every model call inside binds to this unit */ });
```

**Never pick the boundary yourself.** If the user is unsure, say what each choice would
mean for their numbers and let them decide — an unreviewed unit is worse than an
unconfigured one, because it produces confident wrong figures instead of no figures.

### 3. Discover the outcomes — run the scanner, don't hand-read the repo

```bash
valuemaxx onboard --repo .      # read-only: scans, proposes, prints a diff. Writes nothing.
```

It reports **run boundaries** (`generateText`/`streamText`/`createOpenAI`/… — where a
`run(...)` context belongs), **outcome sites** (status setters, `markCompleted`-style
transitions, ORM writes, outbound calls to Stripe/HubSpot/Zendesk), and **entity IDs** in
scope for binding delayed outcomes back.

What it deliberately skips, so you don't have to filter it yourself: test and fixture code
(a test's `markCompleted()` is a fake), and sites at module scope rather than inside a named
function (nothing could bind to them).

**Read the scan critically — it is a starting point, not an answer.** It matches on *names*,
so it cannot tell a business outcome from a same-named utility. Discard anything that isn't
really an outcome, and expect to add outcomes it missed because they don't follow a naming
convention. If a proposal is enormous or mostly noise, say so rather than forwarding it.

If the npm `valuemaxx` binary is missing (`could not determine executable to run`), the
installed version predates the CLI — upgrade, or run the pipeline from a clone.

### 4. GATE — propose the outcomes and wait (the third approval gate)
Present a short summary: *"I found these N outcomes, each run carries this entity ID, these can be bound deterministically and these will be candidate/likely confidence."* Let the human edit/confirm. Then — and only then — write the config.

Keep this list short enough to actually review. Group near-duplicates, lead with the
outcomes that matter to the business, and state plainly which ones you're unsure about.

### 5. Generate the wiring (hybrid — you choose per outcome)
- **in-process outcome** (a function/ORM-write in their app) → a declarative rule in `valuemaxx.outcomes.yaml`. The SDK instruments the named function at `init()`; no per-call-site edits.
- **delayed / external outcome** (a webhook days later) → an explicit captured line in the webhook handler **plus** a `run_id_injection` block so the run_id round-trips and the outcome binds deterministically.
- **entity-id capture** → one `valuemaxx.run(customer_id=...)`-style line at the run entry, using IDs already in scope.

### 6. Validate, then hand off
Call the valuemaxx MCP `validate_*` tools to confirm each rule produces a well-formed, bindable outcome; optionally dry-run against recent traffic to preview `cost-per-<outcome>`. Then deliver everything as a **reviewable diff / PR** — explicit, version-controlled, nothing silent.

## What you must NOT do
- **Don't edit a file before the human approved the file list** (gate 1e). Not "just the
  wrapper", not "just one line to see if it typechecks". Propose, then wait.
- **Don't let an approved scope grow silently.** If the change reaches files that weren't in
  the list you presented, stop and re-ask — especially when threading a parameter through
  intermediate layers, where each hop looks trivial and the total is a cross-codebase
  signature change.
- **Don't run destructive or history-rewriting git commands on their tree** — no `stash`,
  `checkout --`, `reset`, or `clean` to "test something" or undo your own work. You are a
  guest in a working tree that may hold changes that are not yours. Leave reverting to them.
- Don't exfiltrate raw source — emit the proposed config/diff, not the codebase.
- Don't ever echo a secret you encountered while scanning into the diff or logs.
- Don't mark a fuzzy (email/time-window) match as high-confidence — the system owns the confidence label; you only declare the rule.
- Don't change how the human's app works — valuemaxx reads what's already there.
- **Don't weaken a host's safety settings to unblock yourself.** If a lockfile policy, a
  supply-chain guard (npm/bun minimum-release-age), or a CI gate blocks your install, use a
  one-off per-command override or tell the user — never edit the setting.

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
