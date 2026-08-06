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
> 1. **Before anything** (step 2) — they define what one "unit of work" IS. No scan can
>    infer this, getting it wrong silently distorts every cost number, and it decides
>    WHERE capture is wired — so it comes before the wiring, not after.
> 2. **Before writing capture wiring** (step 1e) — you present the exact file list and
>    the reason for each; they approve the scope.
> 3. **Before writing `outcomes.yaml`** (step 4) — they confirm which outcomes are real
>    AND at what GRAIN each is recorded (whole workflow? one step? per item?). The grain
>    is a separate decision from the unit — picking the convenient call site silently
>    answers a question they never saw.
>
> Steps 1 and 2 are written in install-then-boundary order because you must SEE the call
> sites to discuss the boundary. Read both before you edit anything, then gate in the
> order above.
>
> These are someone else's production LLM call path. An agent that "just wires it up" has
> made an unreviewed change to how every model call in their app behaves.

> **You should not need to read valuemaxx's own source to do this.** This skill plus
> [`llms.txt`](../../llms.txt) is the contract: install, capture path, runtime requirements,
> backend, and the outcome scan are all specified below. If you find yourself cloning the
> valuemaxx repo to answer a question about *how to integrate it*, that is a documentation
> bug — tell the user what was missing so it can be fixed.

## The integration, step by step

### 0a. Start from the sentence they said, not from the code

Before scanning anything, write down the user's own words and take them apart. "I want
cost per alt created" is not one requirement — it is three, and each is a separate
decision you must not merge:

| From "cost per **alt created**" | The decision | Where it is settled |
|---|---|---|
| what one unit IS | the run boundary + its id | gate 1 (step 2) |
| what counts as **created** | the outcome site + its GRAIN | gate 3 (step 4) |
| which spend counts toward it | which call sites sit inside the boundary | gate 2 (step 1e) |

They are independent. A workflow-grained unit can carry a step-grained outcome; one run
can produce several different outcomes. Never infer one from another — deciding the unit
does NOT decide the outcome site, and an agent that treats them as one question will
silently pick a grain the user never chose.

Say the interpretation back before you scan: *"you want one number per alt, counted when
the alt reaches ready — not per sprite, and not per build attempt including failures.
Correct?"* A misread here invalidates everything downstream, and it costs one sentence
to check.

### 0. Check whether the repo is already partly wired

Do this before anything else — a half-finished integration is more common than a
greenfield one, and it looks *done* from the outside while producing nothing. Four greps:

```bash
grep -rn "valuemaxx" package.json pyproject.toml   # is the SDK a dependency, at what version?
grep -rn "init(" --include=*.ts --include=*.py . | grep -i valuemaxx   # is capture stood up?
grep -rn "run(" --include=*.ts --include=*.py . | grep -i valuemaxx    # is ANY run boundary wired?
ls valuemaxx.yaml *outcomes.yaml 2>/dev/null   # were the gates ever completed?
# (the outcome file is `valuemaxx.outcomes.yaml`; the glob also catches a bare outcomes.yaml)
```

The revealing combination is **`init()` present, `run()` absent, no `valuemaxx.yaml`**:
capture is live, every call is unbound, and the repo can never reach `exact` tier. It
means an earlier pass wired the easy half and skipped the gates. Do not treat that as
"already onboarded" — the unit-of-work gate is still owed, and it is gate 1.

Report what you found before proposing anything, including the installed version versus
the pinned one. Then run the gates in the normal order; nothing here lets you skip one.

### 1. THE GATEWAY — the default path, and the one to try first

Capture happens in a proxy the host points its provider base URL at. No SDK, no
`init()`, no run boundary, no flush — the request path is unchanged and nothing of
ours runs inside it.

```python
client = OpenAI(
    base_url="https://<gateway>/openai/v1",              # line 1
    default_headers={"x-vmx-key": "vmx_live_...",        # line 2
                     "x-vmx-run-id": order_id},          #   ← THEIR durable id
)
client.chat.completions.create(...,                       # line 3 (optional)
    extra_headers={"x-vmx-outcome": "order_fulfilled"})
```

Routes: `/openai` `/anthropic` `/gemini` `/openrouter`. Every `x-vmx-*` header is
stripped before forwarding; the provider key passes through and is never stored.

**Headers are the entire contract.** Everything the SDK wanted in code is a string:

| Header | Means |
|---|---|
| `x-vmx-key` | the tenant |
| `x-vmx-run-id` (or `baggage: valuemaxx.run_id=…`) | the unit of work |
| `x-vmx-agent` | grouping label |
| `x-vmx-entity-<name>` | durable business ids the unit is about |
| `x-vmx-outcome` | the outcome this call completes (fires only on 2xx) |

**Teach the host's OWN id as `x-vmx-run-id`.** `order_9182`, not a UUID we mint. It
groups a unit's calls *and* makes the delayed join free — when a webhook arrives days
later carrying that id, the outcome binds at `exact` with no window and no inference.
When the host has no such id, the gateway mints one and echoes it back in the
`x-vmx-run-id` response header to stamp outward.

**Outcomes, cheapest first:** the `x-vmx-outcome` header (no extra request); a
`POST <gateway>/v1/outcome` with `{name, run_id | entity}` for a "done" moment with no
adjacent LLM call; an inbound webhook for anything confirmed later. The tier is always
decided server-side.

**When the gateway does not fit** — SigV4/OAuth request signing (Bedrock, Vertex), an
existing OTel collector, or a policy against proxied egress — fall through to the SDK
path below. It is the compat route now, not the front door.

### 1a. SDK path (compat) — install + capture
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

**Language support is not symmetric — check this before promising anything.** Both SDKs
capture cost; they differ at the run boundary, which is what earns `exact`:

| | TypeScript | Python |
|---|---|---|
| `init()` | ✅ camelCase keys | ✅ keyword-only, snake_case (`baggage_targets`, `run_id_injection_specs`) |
| run boundary | ✅ `run(id, opts, fn)` | ✅ `with track.run(run_id=...)` — a contextmanager, imported from `valuemaxx.sdk.track` (not re-exported at top level) |
| `agentName` / `entityKeys` | ✅ | ❌ **not supported** — Python `run()` takes `run_id` only |
| ambient id | `activeRunId()` | `track.active_run_id` (a `ContextVar`) |

```python
from valuemaxx.sdk import track

with track.run(run_id=str(document_id)):
    ...  # model calls here bind to this run
```

Consequence worth stating at the gate: on Python you can bind a run, but you cannot yet
attach entity keys, so a unit that must span SEVERAL runs (cost per customer across
build + screen) is not expressible today. Say that rather than implying parity.

**Any other host language** (Go, Ruby, Java) has no SDK. The only route is emitting OTLP
spans directly to the backend's ingest endpoint. That path is real (`ingest_otlp_span`)
but its span contract — the attribute names carrying model, tokens, tenant and run id —
is not specified in this document. Do not improvise it: report it as a gap and treat the
host as unsupported until the contract is published.

**1a. Pick the capture path — check the host's dependency manifest FIRST.** This is the fork
agents most often get wrong, and picking wrong means capturing nothing:

| The host uses | Capture path |
|---|---|
| Raw `openai` / `@anthropic-ai/sdk` client instances | Pass them to `init({clients: [...]})` |
| **Vercel AI SDK (`ai`, `@ai-sdk/*`) with no raw provider clients** | **`clients` does NOT apply.** Use the tracer (below) |
| LangChain / LlamaIndex / custom HTTP | Tracer path, or OTLP direct |
| **BOTH a raw client and the AI SDK** (common) | Both at once — see below |

`clients` wraps the two provider SDKs *by instance*. An AI-SDK-only codebase has no such
instance to hand it, so the tracer is the ONLY route.

**The paths are not exclusive.** `init()` always stands up the tracer, and *additionally*
patches whatever you pass in `clients`. A repo with a raw `openai` client on one route and
`generateText` on another wires both in a single call — pass the client instances AND use
the returned tracer:

```ts
const vmx = init({ tenantId, ingestKey, endpoint, clients: [{ client: openai, provider: "openai" }] });
// raw-client routes are now patched automatically; AI-SDK routes still need vmx.tracer
```

**LangChain/LlamaIndex is under-specified.** The tracer path is a general OTel tracer, but
this document does not show how to attach one to LangChain's callback system, and there is
no Python `generateText` equivalent to point at. Treat a LangChain host as needing
investigation rather than a solved recipe, and say so at the gate instead of guessing.

The complete TypeScript form:

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

**Do model calls inside `run()` bind automatically?** Yes — on both paths. The span
processor stamps the ambient run id at span *start*, so any model call made inside a
`run()` scope carries it without per-call-site changes. That is the whole point of the
run boundary: you wire it once, not at every call. A call made OUTSIDE any `run()` scope
still captures cost, but binds no run — it is per-model spend, not cost-per-unit.

**Short-lived runtimes (Workers, Lambda).** There is no process exit to flush on. Call
`vmx.forceFlush()` before the isolate can be frozen (e.g. inside `ctx.waitUntil(...)`), or
spans may be dropped. On a **streaming** response the spans are emitted as the stream is
consumed, i.e. *after* the handler returns — flush when the stream settles, not at return.

> **Verify this, do not assume it.** Exposing a `forceFlush` that nothing ever calls is
> the single most common way an integration ends up capturing zero spans while looking
> fully wired. Before you call the wiring done, grep for `forceFlush` and confirm there
> is a real **call site**, not just a definition and a re-export. If the flush handle
> cannot reach a place with `ctx.waitUntil` in scope, say so at the wiring gate — that
> is a scope question for the human, not something to leave dangling.

**Distributed hosts (multi-service, workflow engines, queues).** `run()` binds the run id in
**AsyncLocalStorage**, so it covers one in-process async scope and nothing more. It does NOT
survive an RPC hop, a queue, or a workflow step resumed from persisted state days later. That
matters because the run id is what earns the `exact` binding tier — lose it and everything
downstream degrades to `candidate`/`likely`, which is never billing-grade.

Two carries close the gap, and both are declared at `init()` — you wire nothing per call.
In TypeScript they are `baggageTargets` and `runIdInjectionTargets` (the YAML/Python
spellings are snake_case; the TS config keys are camelCase):

- **Live service→service hop** — `baggageTargets` wraps your outbound HTTP method so the
  active run id rides the W3C `baggage` header; the receiving service parses it back and the
  cascade still binds `exact`. It wraps an outbound **HTTP** call — a transport that is not
  HTTP (an RPC service binding, a queue publish) is not covered by it.
- **Delayed / out-of-process outcome** — `runIdInjectionTargets` stamps the run id into an
  outbound object (e.g. Stripe `metadata`) whose later webhook echoes it back, binding
  `deterministic`.

**Neither carry covers a workflow step resumed from persisted state.** There is no live
call to wrap and no outbound object to stamp — the run id has to be part of what the
engine persists. If the host's engine gives every step a durable instance id, use THAT as
the `run_id_source` and the problem disappears; if it does not, that surface cannot reach
`exact` and you should say so at the gate rather than let the tier degrade silently.

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
Cost is only meaningful per unit — *per invoice processed*, *per ticket resolved*, *per document
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
| Script / batch | the ITEM id if the script fans out (see below); generate one per invocation only if the whole script is one unit |

Ask directly: *"is there an id already in scope at every one of these call sites?"* An
existing id beats a new one — it survives process and service boundaries, which an
in-process scope does not.

**Then test the candidate id for uniqueness — do not trust its name.** An id that looks
right is often not 1:1 with the unit. Two checks, both cheap:

* **Is it stable across the whole unit?** If the user can retry, restart or resume and
  get a *new* id for the *same* unit of work, that id is wrong — you will report two
  half-priced units instead of one. Look for the retry path, not the happy path.
* **Does the schema agree?** A `UNIQUE` constraint tying the id to the business entity
  proves 1:1; a deliberately non-unique index proves the opposite. This is the fastest
  disproof available and it beats reading call sites.
* **Where is the id MINTED?** Go to its construction site, not its use sites. A derived
  id — a hash, a slug, a composite key — is only as stable as its least stable input,
  and that input is often a mutable timestamp two or three hops away. An id built from
  a `created_at` that a retry rewrites looks permanent everywhere it is *read* and
  changes every time the work restarts. Reading the retry route or the state schema
  will not show you this; only the line that constructs the id will.

When the durable anchor turns out to be an entity id rather than a run id (restarts
share an `application_id` but not a `session_id`), you have three options — put them to
the user, do not pick: treat each attempt as its own unit and let the entity key roll
them up later; thread the entity id down to the boundary as the run id; or accept
per-attempt numbers for now and record the limitation.

**One process can produce MANY units — do not let the process boundary decide.** A nightly
job that classifies 10,000 documents has 10,000 units, not one: an invocation-scoped id
would report a single five-figure "cost per nightly run" that answers nothing anybody
asked. The test is whether the items are independent. If each item is separately
meaningful — a document, an invoice, a candidate — then the ITEM id is the run id and
`run()` is called per item, inside the loop. Generate a per-invocation id only when the
whole script really is one unit (a single report, one summary of everything).

Per-item calls are the intended shape at any volume, and each one is a scope entry, not
a network call. If a partial rerun can reprocess the same items, note that units are
identified by that item id — reprocessing the same document is the same unit again, and
you should tell the user whether they want that deduplicated or counted twice.

**Before declaring an id out of scope, check what the call site already loads.** "It is
not in the session/context object" is not the same as "it is not available": handlers
routinely fetch a row, a job record, or a document that carries the durable id as a
plain column, and a parse over the whole row hands it to you for free. Look at what the
nearest fetch actually returns, not just at the object the framework threads through.
The difference decides whether the honest boundary costs one field access or a
signature change across files — so it is worth two minutes before you present options.

**If no id is in scope at all**, say so and stop. Threading one through intermediate
layers is a signature change across files — exactly the scope growth the wiring gate
forbids. Offer to leave that surface uncaptured and record it as a known gap; a missing
surface is honest, a rushed refactor is not.

Then resolve **entity keys** — the durable business ids the unit is about (`invoice_id`,
`ticket_id`, `loan_id`). These are what let a unit span SEVERAL runs later, and they
**cannot be backfilled**: history recorded without them stays unattributable. Say that
plainly, because it is the one decision with a deadline.

**Ground the choice in a number before accepting it.** Once capture has run briefly,
show what the boundary implies — *"with this boundary your last 20 runs averaged
$0.02 each; a stage boundary would say $0.0025"* — and let them confirm the one that
matches their intuition. A boundary nobody has sanity-checked is a guess with a
dollar sign in front of it.

**A codebase may have several units, and most non-trivial ones do.** A repo with a
workflow engine, a chat surface and a cron job has three different answers, and forcing
them into one produces a number that describes nothing. `units` is a LIST. Enumerate
every LLM-using surface you found in step 1, group them by the unit a user would
recognise, and present the grouping for correction — the grouping is the decision, and
it is theirs.

Do not propose more units than a person can review in one sitting. If you find a dozen
surfaces, propose the two or three that carry real spend, and list the rest as
deliberately uncaptured.

Write the answer to `valuemaxx.yaml` so it is reviewable, diffable and re-runnable:

```yaml
# Example only — a support desk with two surfaces. Their nouns, not yours.
units:
  - name: ticket_resolved                  # what one unit is called, in their words
    run_id_source: ctx.workflowInstanceId  # the value identical across the unit —
                                           # note a RETRIED workflow is a new instance,
                                           # so this counts each attempt separately.
                                           # Fine if that is what they want; use the
                                           # entity id instead if retries must roll up.
    entity_keys: [ticket_id, account_id]   # durable ids the unit is about (optional)
    surfaces: [triage, draft-reply]        # which call sites roll up here

  - name: doc_indexed                      # a second, unrelated unit — one PER DOCUMENT,
    run_id_source: document.id             # so the run id is the document, not the job
    entity_keys: [document_id]
    surfaces: [nightly-ingest]
```

`run_id_source` is documentation, not executable — it records WHICH value was agreed so
a later reader can check the wiring still matches. The binding itself is the `run()`
call. Keep the two in sync by hand; nothing enforces it.

Wire each unit at its own run boundary — one call per unit, not per call site:

```ts
// The signature — both forms are real overloads; the options object is optional.
function run<T>(runId: string, fn: () => T): T;
function run<T>(runId: string, options: RunOptions, fn: () => T): T;

interface RunOptions {
  readonly agentName?: string | undefined;
  readonly entityKeys?: Readonly<Record<string, string>> | undefined;
}
```

`run()` returns whatever the callback returns, so it wraps a sync or an async function
without changing the host's control flow — `await run(id, async () => …)` works because
the promise is passed straight through, not because `run` is itself async.

```ts
// <runId> is the agreed run_id_source; <unitName> and the entity keys are theirs.
await run(runId, { agentName: "<unitName>", entityKeys: { <entity_id>: value } },
  async () => { /* every model call inside binds to this unit */ });
```

**`entity_keys` in the YAML are NAMES; `entityKeys` in the call are NAME→VALUE.** The
config records which keys were agreed; the call supplies that run's actual ids. Keep the
names identical between the two — nothing enforces it, and a typo produces a key that
silently never joins to anything. Since entity keys cannot be backfilled, a mismatch is
permanently costly.

A surface that no unit claims is uncaptured, and that is a legitimate outcome — just
name it in the file so the gap is deliberate rather than forgotten.

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

### 4. GATE — propose the outcomes AND their grain, then wait (the third approval gate)
Present a short summary: *"I found these N outcomes, each run carries this entity ID, these can be bound deterministically and these will be candidate/likely confidence."* Let the human edit/confirm. Then — and only then — write the config.

Keep this list short enough to actually review. Group near-duplicates, lead with the
outcomes that matter to the business, and state plainly which ones you're unsure about.

**Grain is a separate question from the unit, and it is theirs to answer.** The run
boundary decides what cost is grouped; the outcome site decides what that group is
divided by. Both are legitimate at more than one level, and picking the convenient site
silently answers a question the user never saw:

| Grain | Records when | Answers |
|---|---|---|
| whole workflow / job | the run reaches its terminal state | "what does one finished thing cost me?" |
| a single step / stage | one stage inside the run succeeds | "which stage is the expensive one?" |
| an item inside a batch | each item is processed | "what does one item cost?" |
| an external confirmation | a webhook/invoice later confirms it | "what did the outcomes that STUCK cost?" |

These compose — the same runs can carry a workflow-grained outcome AND a step-grained
one, answering pricing and optimization questions respectively. So ask which they want,
plural, rather than treating it as a single choice.

Two consequences worth stating plainly when you ask, because they change the number:

* **A coarser grain counts failures.** If the outcome fires only on success but the run
  boundary spans the whole attempt, failed work stays inside the unit's cost and raises
  the per-unit number. That is usually correct — failures are a real cost of producing
  successes — but the user should choose it, not inherit it.
* **A finer grain multiplies the denominator.** Ten sprites inside one alt make
  "cost per sprite" ten times smaller than "cost per alt", and neither is wrong. Show
  both numbers if you can; a grain nobody has seen the arithmetic for is a guess.

Then find the SITE for each confirmed grain and show it: file, function, and the exact
moment. If the host has no patchable function there, say so and propose
`recordOutcomeNow` at that moment instead — do not quietly relocate the outcome to
wherever wiring happens to be easy, because the site IS the grain.

### 5. Generate the wiring (the MECHANISM is yours; the site and grain are theirs)

Gate 3 settled *what* is recorded and *where*. This step is only about which of the
four mechanisms below reaches that already-agreed site. If you find yourself moving the
site to suit a mechanism, you are re-deciding gate 3 on the user's behalf — stop and
re-ask instead.

- **in-process outcome** (a function/ORM-write in their app) → a declarative rule in `valuemaxx.outcomes.yaml`. The SDK instruments the named function at `init()`; no per-call-site edits.
- **in-process outcome with nothing to patch** → `recordOutcomeNow({ name }, config)`, called at the moment the work succeeds. The declarative path needs a named FUNCTION on an object the SDK can wrap; a workflow step that reaches its terminal state as a RETURN VALUE, a queue consumer that acks a message, or a chat turn that resolves a completion owns no such function. Check this before promising the declarative route — a host can bind runs perfectly and still never record the outcome those runs exist to explain, which reads as "no data" rather than "not wired". It rejects on a failed POST (a direct caller can `try`/`catch`), so wrap it: recording an outcome must never break a working feature.
- **delayed / external outcome** (a webhook days later) → an explicit captured line in the webhook handler **plus** a `run_id_injection` block so the run_id round-trips and the outcome binds deterministically.
- **entity-id capture** → one `valuemaxx.run(customer_id=...)`-style line at the run entry, using IDs already in scope.

### 6. Validate
Call the valuemaxx MCP `validate_*` tools to confirm each rule produces a well-formed, bindable outcome; optionally dry-run against recent traffic to preview `cost-per-<outcome>`.

Then prove the loop end to end BEFORE you hand it over, because each half looks healthy
while the other is missing: capture with no outcome renders a null cost-per-outcome that
reads as "no traffic", and an outcome with no bound run renders the same null for the
opposite reason. Check all three, and say which you could not check:

1. a cost span reaches the backend (the endpoint is set and a flush actually runs);
2. an outcome is recorded — grep the repo for a real call site, do not assume the
   config file implies one;
3. the two join: the outcome binds at `exact`/`deterministic`, not `UNBOUND`.

If you verified with hand-made requests rather than the host's own code, say so
explicitly. A number produced by your own curl proves the backend arithmetic and
nothing about the integration.

### 7. Branch and open a PR
Never leave the work on whatever branch happened to be checked out. Cut a fresh branch
from **remote** main (`git fetch` first — not local main, which may be stale or carry
someone else's work), commit there, push, and open a PR.

Check `git status` before you start: a dirty tree means changes that are not yours, and
they must not end up in your commit or your branch. If the tree is dirty, say so and ask
— do not stash it, do not commit around it, do not "clean up" first.

The PR body should state what a reviewer cannot infer from the diff: which unit and
grain were agreed and why, which surfaces were deliberately left uncaptured, and what
still has to happen before numbers appear (setting the endpoint/tenant/ingest secrets is
almost always outstanding, and nothing is emitted until it is done).

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
