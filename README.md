# valuemaxx

**stop tokenmaxxing. start valuemaxxing.** — *the anti-tokenmaxxing tool*

> **Know what each AI agent actually costs you — correctly — and what it earned, per outcome, with confidence.**
> For teams that **build** AI agents, not the ones who buy them.

Observability tools (Helicone, Langfuse) tell you what you **spent**. This tells you whether it was **worth it**: it captures *correct, invoice-reconciled* LLM cost per agent run, deterministically binds it to the real business outcome each run produced — including outcomes that arrive days later, out of process — and labels every number with how trustworthy it is. Then it shows you, on your real workload, where a cheaper or faster model holds the same outcome.

---

> **For AI agents / crawlers:** machine-readable capability + usage info is in [`llms.txt`](./llms.txt); integration guidance is in [`docs/onboarding/`](./docs/onboarding/) (a Claude Code Skill + ready-to-paste prompts).

## Why this exists

If you build an AI product (a support agent, an SDR agent, an AI feature), your tokens *are* your cost of goods. Most homegrown cost numbers are wrong by 8–15% (streaming-disconnect undercounts, invisible retries, mis-priced cache tokens). And almost nobody can answer "did this agent run actually make money?" — because the cost lives in your logs and the outcome lives in your product or your CRM.

This tool closes both gaps, and it's honest about precision the whole way: every figure carries a **provenance** (was it measured, estimated, or reconciled to the invoice?), every cost↔outcome link carries a **binding tier** (exact key, deterministic round-trip, fuzzy match), and every outcome carries a **signal class** (did the action just *happen*, or is the business result *confirmed*?).

## How it works (the short version)

1. **`init()` — one line.** A thin SDK (Python *and* TypeScript) captures every LLM call's *correct* cost, off the hot path, and never throws into your app.
2. **Declare your outcomes once.** A config (`outcomes.yaml`) — which the onboarding agent writes for you by reading your codebase — says what a "resolution" / "deal" / "funded loan" *is* in your system. No per-call tracking code.
3. **Cost binds to outcome automatically — the SDK does the plumbing.** `init()` installs three carry channels for the active run id, so binding needs no per-call tracking code: **in-process** via execution context (`exact`); **across a live service hop** via W3C baggage the SDK stamps on outbound HTTP (`exact`); and **delayed/out-of-process** via a round-tripped correlation id the SDK stamps on your outbound call (e.g. Stripe metadata) that the webhook echoes back (`deterministic`). Where no id can be carried, it falls back to a *labeled* entity/time match — never a silent mis-bind. Everything is confidence-labeled.
4. **See your margin, and where to cut it.** Cost-per-outcome and gross-margin rollups; and an eval layer that replays cheaper models against your real workload and recommends switches — with the evidence, never automatically.

---

## Getting started

This walks you from nothing to a real cost-per-outcome number, end to end, against the backend that ships in this repo. Every command below runs as written.

The backend is a real FastAPI app over **SQLite** (no Postgres needed for local dev); migrations run on startup. You boot it with `valuemaxx up`, send it cost spans on the wire, and query the numbers back over HTTP (or the SDK / CLI).

> **One install per language; the same commands.** `pip install valuemaxx` and `npm install valuemaxx` both give you the **SDK** (`init()` capture) **and** the `valuemaxx` command with **`onboard`** + `init` — so `valuemaxx onboard` works identically on either side (only npm vs pip differs). The **backend** (`valuemaxx up` + the query commands) is heavier: it comes with `pip install "valuemaxx[cli]"`, or — the language-neutral, recommended way — you run it as a container (`docker run …`). So a TypeScript project never has to touch Python.

### 0. Install

```bash
# Python: the SDK (init() capture) + the `valuemaxx` command (onboard / init)
pip install valuemaxx
```

```bash
# TypeScript / JavaScript: the same — SDK + the `valuemaxx` command (onboard / init)
npm install valuemaxx
```

Both give you `valuemaxx onboard`. The **backend** (`valuemaxx up` + query commands) is separate — either `pip install "valuemaxx[cli]"`, or run the container (step 1). Working from a clone instead? Prefix `valuemaxx …` with `uv run` (Python) or run the built bin (TS); the commands are identical.

### 1. Boot the backend

valuemaxx has two pieces: the **SDK** (above — the library you import, per-language) and the **backend** — *one* service that receives the cost your SDK sends, stores it, reconciles it, and answers the metric queries. The backend is the same regardless of your app's language; you run it once and point any SDK (TS or Python) at it. Pick whichever way to run it:

**Docker (recommended — no Python needed; ideal for TS/JS apps):**

```bash
docker run -p 8000:8000 ghcr.io/monaal10/valuemaxx-backend   # (until published: docker build -t valuemaxx-backend . && docker run -p 8000:8000 valuemaxx-backend)
# serving on http://0.0.0.0:8000 — using dev key "dev" (send header "X-API-Key: dev")
```

For a persistent Postgres-backed store, `docker compose up` (bundles backend + Postgres; see [`docker-compose.yml`](./docker-compose.yml)).

**Or, if you have Python — `valuemaxx up`** (same backend, in-process). **Zero config:** it opens an embedded SQLite database (`./valuemaxx.db`), runs migrations, generates a stable local **`dev` ingest key**, and serves:

```bash
valuemaxx up
# valuemaxx up: serving on http://127.0.0.1:8000 (db=sqlite+aiosqlite:///./valuemaxx.db)
# valuemaxx up: no ingest key configured — using dev key "dev" (send header "X-API-Key: dev"). …
```

Use `X-API-Key: dev` on every request below — that's all the auth you need locally. The `dev` key is **stable across restarts**, so data you persist stays readable.

When you're ready to use your own key(s) — or run multi-tenant — set `VALUEMAXX_INGEST_KEYS` (a JSON map of `key → tenant UUID`); that turns the `dev` fallback off:

```bash
export VALUEMAXX_INGEST_KEYS='{"my-key": "6f1c3b2a-0000-4a00-8000-000000000001"}'
```

`--host`, `--port`, and `--db` (or `DATABASE_URL` / `VALUEMAXX_DATABASE_URL`) override the defaults. Point `--db` at a `postgresql+asyncpg://…` URL for a persistent multi-process backend. Leave this running; the rest of the steps talk to it.

**A "tenant" is one isolated account** — for a solo dev or a single-product team that's just *you* (one tenant), and you never type a tenant id: it's resolved from your ingest key, never read from the request body, so a caller can only ever act on its own tenant. You'd use multiple tenants only if you need hard data isolation between separate accounts (e.g. an agent vendor hosting several customers' cost data); your *own* customers are modeled as outcomes/entities inside one tenant, not as tenants.

> **MCP, for free.** The running backend also speaks the **Model Context Protocol** at `POST /mcp` — every capability that declares the MCP surface is a tool. Point your MCP client (Claude Desktop/Code) at `http://127.0.0.1:8000/mcp` (authenticated with your ingest key in the `x-valuemaxx-ingest-key` header) and an agent can call `validate_outcome_rule`, `run_metric`, `cost_breakdown`, … directly. No separate install — it's a URL on the backend you already booted.

### 2. Wire the SDK into your agent

Add one call at your process entrypoint so every LLM call gets correct-cost capture, and wrap each agent run so its cost binds to a run id.

**Python** — `init()` validates your config and stands up capture; `track.run(run_id=…)` binds the ambient run:

```python
from uuid import UUID
import valuemaxx.sdk as valuemaxx

vmx = valuemaxx.init(
    tenant_id=UUID("6f1c3b2a-0000-4a00-8000-000000000001"),  # your tenant UUID
    ingest_key="dev",
    endpoint="http://127.0.0.1:8000",
)
print(vmx.effective.endpoint, vmx.capture_granularity, vmx.warnings)

# Bind a run so every captured LLM call inside it shares one run id:
with valuemaxx.track.run(run_id="checkout-agent-42"):
    ...  # your agent's LLM calls
```

`init()` **never throws into your app** (fail-open, H9): a bad literal config raises at the call site, but every instrumentation step thereafter is caught, logged, and surfaced as a warning. `tenant_id` is a real `UUID`. Cost capture instruments the *injected provider client's* transport instance-scoped (so an unrelated `httpx.Client` in your process is never touched); see [`sdks/python`](./sdks/python) for the client/sink wiring the SDK uses to land a captured call as a cost event.

Beyond `track.run` (which carries the run id **in-process**), `init()` also installs the two deterministic *carry* channels so cost binds to outcomes that land elsewhere — you wire nothing per call:

```python
vmx = valuemaxx.init(
    tenant_id=UUID("6f1c3b2a-0000-4a00-8000-000000000001"),
    ingest_key="dev",
    endpoint="http://127.0.0.1:8000",
    # T2 — stamp the run id on W3C baggage for outbound HTTP (a live service→service hop):
    baggage_targets=["httpx.Client.request", "httpx.AsyncClient.request"],
    # T3 — stamp the run id into an echoing SDK call (round-trips via its later webhook).
    # These specs come straight from `valuemaxx onboard`'s outcomes.yaml — you don't hand-write them:
    run_id_injection_specs=onboarded_injection_specs,
)
```

Both fail open and are **reported, never silent**: a target that isn't importable at `init()` is named in `vmx.warnings` (so a wrong import order can't quietly disable the round-trip), and with no active run the call passes through untouched. The TypeScript `init()` takes the symmetric `baggageTargets` / `runIdInjectionTargets` options and stamps the **byte-identical** baggage header (pinned by a cross-language parity test).

Prefer to have it scaffolded for you? From your repo root:

```bash
valuemaxx init                 # detect your framework, print a reviewable diff (review-only)
valuemaxx init --apply         # write the (reversible) init() wiring into your entrypoint
```

**TypeScript** — `init()` builds a real OTLP/HTTP exporter pointed at your endpoint and returns a `tracer`. There are two ways to wire it, depending on how you call models:

*Using the **Vercel AI SDK** (`generateText`/`streamText`) — the common case:* pass the returned `tracer` to `experimental_telemetry`, and every call is captured:

```ts
import { generateText } from "ai";
import { init } from "valuemaxx";

const vmx = init({
  tenantId: "00000000-0000-4000-8000-000000000001", // the dev tenant (from the backend)
  ingestKey: "dev",
  endpoint: "http://localhost:8000", // the backend from step 1
});

await generateText({
  model /* your @ai-sdk/* model */,
  prompt: "…",
  experimental_telemetry: { isEnabled: true, tracer: vmx.tracer },
});
```

*Calling the **OpenAI/Anthropic/Google clients directly** instead?* pass them to `init({ clients })` and it instruments them in place — no per-call-site edit:

```ts
import OpenAI from "openai";
import { init, run } from "valuemaxx";

const openai = new OpenAI();
init({ tenantId: "00000000-0000-4000-8000-000000000001", ingestKey: "dev", endpoint: "http://localhost:8000", clients: [{ client: openai, provider: "openai" }] });

await run("checkout-agent-42", async () => {
  await openai.chat.completions.create({ model: "gpt-4.1", messages: [/* … */] });
});
```

Streaming cost is accumulated to **terminal** token values across chunks before the span is emitted (no delta-summing, no cache double-counting). Full options + the wire contract are in [`sdks/typescript/README.md`](./sdks/typescript/README.md).

### 3. Send a cost span to the backend

The SDK ships cost to the backend's **OTLP/HTTP collector** at `POST /v1/traces` — a standard OpenTelemetry trace exporter, authenticated with your ingest key in the `x-valuemaxx-ingest-key` header (the OTLP exporter sends only the key; it doesn't HMAC-sign). The tenant is resolved from the key — never the body. Re-delivering the same `(run_id, attempt_id)` upserts, so it never double-counts.

When you wire `init()` (step 2) the exporter does this automatically. To prove the loop by hand, POST one OTLP span — exactly the wire shape the SDK exporter emits (note OTLP-JSON encodes integer attribute values as strings):

```bash
curl -s http://127.0.0.1:8000/v1/traces \
  -H "x-valuemaxx-ingest-key: dev" -H "Content-Type: application/json" \
  -d '{"resourceSpans":[{"scopeSpans":[{"spans":[{"name":"ai.generateText","attributes":[
        {"key":"gen_ai.system","value":{"stringValue":"anthropic"}},
        {"key":"gen_ai.request.model","value":{"stringValue":"claude-opus-4-8"}},
        {"key":"gen_ai.usage.input_tokens","value":{"intValue":"100"}},
        {"key":"gen_ai.usage.output_tokens","value":{"intValue":"50"}},
        {"key":"ai_margin.run_id","value":{"stringValue":"checkout-agent-42"}},
        {"key":"ai_margin.attempt_id","value":{"stringValue":"attempt-1"}},
        {"key":"ai_margin.cost_usd","value":{"stringValue":"0.0250"}}
      ]}]}]}]}'
# {}  — an empty body is the OTLP success response: the span was accepted and persisted.
```

### 4. Query your cost

Query the persisted cost back over the HTTP API. `run_metric` is a typed, closed-allowlist DSL (`filter → outcome → join → measure`); the result carries the conservative confidence (`minimum_tier` + distribution) on every cell.

**Total cost (the cost-per-outcome metric):**

```bash
curl -s http://127.0.0.1:8000/run_metric \
  -H "X-API-Key: dev" -H "Content-Type: application/json" \
  -d '{"name":"cost_per_outcome","numerator":"total_cost_usd",
       "denominator":"verified_outcome_count","filters":{},"group_by":[]}'
# {"name":"cost_per_outcome","cells":[{"group_key":[],
#   "numerator_value":"0.0250000000","denominator_value":0,"value":null,
#   "confidence":{"minimum_tier":"likely","confidence_distribution":{"likely":1}},
#   ...}],"requires_reemit":false}
```

The `numerator_value` is the summed cost of every persisted cost event in your tenant scope — exactly what you ingested. `value` (the cost-*per*-outcome ratio) is `null` until outcomes are bound (step 5): the billing-grade denominator is `verified_outcome_count`, which counts only *confirmed* outcomes bound at an exact/deterministic tier, so advisory and retracted outcomes can never inflate it.

**Cost broken down by model** — same call, grouped:

```bash
curl -s http://127.0.0.1:8000/run_metric \
  -H "X-API-Key: dev" -H "Content-Type: application/json" \
  -d '{"name":"cost_by_model","numerator":"total_cost_usd",
       "denominator":"verified_outcome_count","filters":{},"group_by":["model"]}'
# one cell per model: [["model","claude-opus-4-8"]] -> "0.0250000000"
```

You can also group by `provider`, `agent_name`, `outcome_name`, or `tenant`. (A `total_cost_usd` numerator always requires the `verified_outcome_count` denominator — that's the H8 rule that keeps the cost-per-outcome denominator billing-grade.)

### 5. Declare an outcome

Cost-per-outcome needs to know what an *outcome* is in your system. That's `outcomes.yaml`: a list of rules, each with a `match` (one of `function` / `http` / `orm_save` / `status_transition` / `webhook`) and an optional `when` predicate over a fixed, safe namespace (`args`, `kwargs`, `result`, `data`, `instance`, `event` — never `eval`'d).

```yaml
# outcomes.yaml
version: 1
outcomes:
  # A support ticket is "resolved" when your code transitions its status.
  - name: ticket_resolved
    match:
      status_transition: SupportTicket.status
      when: result.status == "resolved"
    signal: outcome_confirmed

  # A delayed, out-of-process outcome: Stripe confirms the charge via webhook.
  # `init()` auto-stamps run_id on the outbound call (T3); the webhook echo reads it back.
  - name: payment_succeeded
    match:
      webhook: stripe
      event: payment_intent.succeeded
    signal: outcome_confirmed
    run_id_injection:
      sdk_call: stripe.PaymentIntent.create
      inject_into: metadata.atm_run_id
      webhook_event: payment_intent.succeeded
      extract_from: data.object.metadata.atm_run_id
```

The `run_id_injection` block is **executed, not just documented**: pass these specs to `init(run_id_injection_specs=…)` (step 2) and the SDK wraps `stripe.PaymentIntent.create` so every call inside a `track.run` carries the run id in `metadata.atm_run_id` — copy-on-write, so your own kwargs are never mutated. When Stripe's webhook echoes it back, the outcome binds `deterministic` (billing-grade). If the external system *doesn't* echo metadata (e.g. Salesforce), onboarding omits the block and the outcome falls back to a **labeled** entity-match — never silently mis-bound.

Have the onboarding scan write this for you, or validate a hand-written file. `valuemaxx onboard` comes with the base install on **both** languages (`pip install valuemaxx` / `npm install valuemaxx`) and behaves identically — it scans TypeScript *and* Python, proposes `outcomes.yaml`, and prints a reviewable diff (nothing is written; rules stay UNCONFIRMED):

```bash
# Scan your repo -> propose outcomes.yaml + a reviewable diff. Same on TS and Python.
valuemaxx onboard --repo .

# Validate / summarize a hand-written outcomes.yaml (rejects any eval/exec predicate)
TENANT=6f1c3b2a-0000-4a00-8000-000000000001
Y=$(python3 -c "import json;print(json.dumps(open('outcomes.yaml').read()))")
valuemaxx validate-outcome-rule --tenant "$TENANT" --json-input "{\"yaml_text\": $Y}"
# {"error": null, "ok": true, "rule_count": 2}
valuemaxx list-outcome-rules   --tenant "$TENANT" --json-input "{\"yaml_text\": $Y}"
# one summary per rule: name, match_kind, signal
```

The signal class is **system-owned**: a bare function/HTTP write is only `action_attempted`; a status transition, ORM write, or webhook echo can confirm an outcome. You can never make an attempt masquerade as a confirmed result.

### 6. See cost-per-outcome

Once your agent runs with confirmed outcomes bound to their runs (in-process via `track.run`, or out-of-process via the round-tripped `run_id`), the same `run_metric` query returns a real ratio: the `value` field becomes `total_cost ÷ verified_outcome_count`, and every cell still carries its `minimum_tier`. Group by `outcome_name` or `agent_name` to see margin per outcome or per agent.

### 7. Right-size your models (later, once you have real data)

With cost bound to outcomes over some real traffic, the eval layer replays **cheaper candidate models you supply** against your captured workload and tells you whether one holds the same outcome — with the evidence, and **never switching automatically**. Because eval runs spend your provider tokens, it estimates the per-candidate cost and gates on an explicit approval first:

```bash
valuemaxx run-eval-funnel      # replay your candidates on the captured workload (cost-gated)
valuemaxx approve-gate         # record the "yes, spend ~$X on this eval" approval
valuemaxx get-recommendation   # the cheaper-model-holds-your-outcome report
```

That's the whole loop: **install → run the backend → wire the SDK → run your agent (send cost) → query cost → declare outcomes → cost-per-outcome → right-size the model.**

---

## The honesty model

Three system axes ride every number and never get laundered upward (a rollup always shows the *least-trusted* of its parts):

| Axis | Values |
|---|---|
| **Cost provenance** | `measured` · `estimated` · `allocated` · `provider_reconciled` · `manual_reconciled` |
| **Binding tier** | `exact` · `deterministic` · `candidate` · `likely` |
| **Outcome signal class** | `action_attempted` · `outcome_confirmed` · `outcome_retracted` |

Reconciliation to the invoice is **additive** (a new record, never an overwrite of the estimate); a retracted outcome is **removed from the cost-per-outcome denominator** and the metric re-emitted, never silently left.

## Self-hosting & data

Runs on a container + Postgres (`postgresql+asyncpg://…`), or embedded SQLite for local dev — `valuemaxx up` defaults to SQLite so it boots with zero configuration. Prompt/response **content is off by default**; it's only retained (self-host only) if you enable it for the eval/replay features, with a configurable TTL and an erasure path. Provider API keys for eval are **never persisted**, and ingest keys / webhook secrets are never logged.

## Integrate with an AI coding agent (Claude Code / Cursor)

This project is built to be wired up **by** a coding agent. `valuemaxx onboard` runs the onboarding pipeline (scan → propose → render → reviewable diff): it scans your codebase, finds where your agent runs and where outcomes are recorded, proposes the `outcomes.yaml`, and prints a reviewable diff. For each *echoing* external write (Stripe, HubSpot…) it also proposes a `run_id_injection` block — the exact spec you hand to `init(run_id_injection_specs=…)` so the SDK auto-stamps the run id on that outbound call and the later webhook binds it `deterministic` (a non-echoing system like Salesforce is instead flagged as a labeled fallback). The scanner and the proposed output are **identical across TypeScript and Python** (one shared rules contract + a golden cross-language parity test). The candidate rules stay **unconfirmed** until you approve the diff. See [`docs/onboarding/`](./docs/onboarding/) for the onboarding prompts and the skill.

## Contributing

Engineering standards are strict and binding — see [`AGENTS.md`](./AGENTS.md): test-driven development (unit + integration + e2e), `pyright --strict` + `ruff`, ≥90% coverage on core, and a **ratchet** discipline (every bug becomes a permanent conformance rule so its class can't recur).

## License

Apache-2.0 — see [`LICENSE`](./LICENSE).
