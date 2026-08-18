# valuemaxx

**Know what the AI you ship actually costs — per real business outcome — and where to make it cheaper without losing the outcome.**

*For engineering and product teams running LLM features in production, who can see their provider bill but not what it bought.*

[![CI](https://github.com/monaal10/valuemaxx/actions/workflows/ci.yml/badge.svg)](https://github.com/monaal10/valuemaxx/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/valuemaxx?label=pypi)](https://pypi.org/project/valuemaxx/)
[![npm](https://img.shields.io/npm/v/valuemaxx?label=npm)](https://www.npmjs.com/package/valuemaxx)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](./LICENSE)

Your provider invoice says you spent $82,400 last month. It cannot tell you that this was **$19.54 per meeting booked**, that 38% of it produced no outcome at all, or that a cheaper model would hold the same booking rate.

valuemaxx answers those three questions:

1. **What does one outcome cost?** — cost per ticket resolved, per deal closed, per document processed. Captured correctly, including streaming, cached tokens and calls the client disconnected from.
2. **How much should you trust that number?** — every figure carries system-owned labels for how the cost was measured, how strongly it was linked to the outcome, and whether that link was *observed* or merely *inferred*. A caller states what happened; it never states how much to trust the link.
3. **What would make it cheaper?** — a candidate model is compared on cost **per outcome**, not per token, and a switch is only called safe when a properly powered test says the outcome rate held.

The outcome can arrive days later, in another process, under a different id — a CRM confirming a deal, a webhook marking a ticket resolved. That case is the reason this exists, and most of the engineering here is about getting it right.

---

> **For AI agents / crawlers:** machine-readable capability + usage info is in [`llms.txt`](./llms.txt); integration guidance is in [`docs/onboarding/`](./docs/onboarding/) (a Claude Code Skill). Both lead with the same two primitives described below.

## Why this exists

If you build an AI product, your tokens *are* your cost of goods. Most homegrown cost numbers are wrong by 8–15% (streaming-disconnect undercounts, invisible retries, mis-priced cache tokens). And almost nobody can answer "did this agent run actually make money?" — because the cost lives in your logs and the outcome lives in your product or your CRM.

valuemaxx closes both gaps, and it is honest about precision the whole way: every figure carries a **provenance**, every cost↔outcome link a **binding tier**, every outcome a **signal class** — all system-owned. A caller states what happened; it never states how much to trust the link.

## How it works — two primitives

Everything reduces to two things, and both are expressible in curl:

**1. Cost flows through the gateway.** An observe-only reverse proxy in front of your LLM provider. Swap your `baseURL`, keep your provider key (it passes through, never stored), and every call's correct cost is captured server-side — streaming, cache tokens, and client-disconnect recovery included. Nothing of ours runs inside your request path, and any gateway failure falls back to a plain passthrough: losing a span is acceptable, losing your request is not.

**2. Outcomes are one event.** At the moment a business fact becomes true, *some* code of yours is executing with the relevant business id in a variable — the one invariant every architecture shares. Deliver the tuple there:

```
POST <gateway>/v1/outcome
{ "name": "order_fulfilled", "run_id": order_id, "identifier": evt_id, "value": 129.00 }
```

Everything else — the `x-vmx-outcome` header, inbound webhooks, settle rules, decorators — is a shortcut that emits this same event. The docs never say "for workflow codebases, do X": if your shape matches a shortcut it's one line instead of three, and nothing beyond the tuple is ever required.

## Getting started (~5 minutes; 3 lines for capture, ~15 for a delayed outcome)

### 0. Run the two pieces

```bash
# the brain: FastAPI over SQLite (Postgres in prod), migrations on startup
docker run -p 8000:8000 -v vmx-data:/home/valuemaxx/data \
  ghcr.io/monaal10/valuemaxx-backend:latest
# or, with Python: pip install "valuemaxx[cli]" && valuemaxx up

# the front door: a Cloudflare Worker (portable fetch/streams code — any edge runtime works)
cd gateway && bunx wrangler deploy --var VALUEMAXX_BACKEND:https://<your-backend>
```

Your key is whatever `VALUEMAXX_INGEST_KEYS` maps (`{"<key>": "<tenant-uuid>"}`); with none configured the backend serves a single dev key, `dev`.

### 1. Swap the base URL — capture begins

```python
client = OpenAI(
    base_url="https://<gateway>/openai/v1",
    default_headers={"x-vmx-key": "vmx_..."},
)
```

Routes: `/openai` · `/anthropic` · `/gemini` · `/openrouter` (whose authoritative billed cost is recorded as `provider_reconciled`, never an estimate). Every `x-vmx-*` header is stripped before forwarding — the provider sees exactly the request you wrote. The dashboard already shows spend by model and agent.

**If you stream from OpenAI, set `stream_options={"include_usage": True}` on those calls.** OpenAI omits the usage block from a stream unless the caller asks for it, so there is nothing for the gateway to read and the calls capture zero tokens. We deliberately do not add the flag for you: injecting it would change the request, and "the provider sees exactly the request you wrote" is the invariant the whole design rests on. The gateway detects that you did not set it and marks those spans `partial_recovered` rather than reporting a confident zero — but the fix is one argument on your side. Anthropic and Gemini always report usage; this applies to OpenAI (and OpenAI-compatible) streaming only.

### 2. Name your unit of work

```python
default_headers={..., "x-vmx-run-id": order_id, "x-vmx-agent": "support-bot"}
```

Use **your own durable business id**, not a minted UUID. All calls sharing it group into one unit, retries roll up instead of double-counting, and the delayed outcome join is free — that id already flows through your Stripe metadata and your CRM because it is yours. (Send nothing and the gateway mints an id, echoing it back in the `x-vmx-run-id` response header for you to stamp outward.) `x-vmx-entity-<name>` headers attach durable ids that let one unit span several runs.

### 3. Deliver the outcome

```python
# shortcut — the producing call IS the outcome (fires only on 2xx):
client.chat.completions.create(..., extra_headers={"x-vmx-outcome": "reply_sent"})

# universal form — any language, any framework, no SDK:
requests.post(f"{GW}/v1/outcome", headers={"x-vmx-key": KEY},
    json={"name": "order_fulfilled", "run_id": order_id, "identifier": evt_id})
```

Contract discipline: a duplicate `identifier` is accepted-and-ignored, so at-least-once senders (retries, replays, webhook redelivery) never inflate a denominator; `occurred_at` outside 35 days back / 5 minutes forward is a 422, not a silent clamp; `?strict=true` rejects an event with no join key (default stays permissive — unbound-but-visible beats silently dropped).

**Check `attached` on your first call.** Every reply carries `attached`, `attachment` (`run_id` / `entity` / `run_unmatched` / `entity_unmatched` / `none`) and, when it did not attach, a `hint` naming what you can change. A 200 alone does not mean the event found its cost — an outcome that matched nothing looks identical to a successful one otherwise, and stays invisible until someone notices the denominator is too small.

If the outcome binds by **entity** rather than `run_id` and your lag is long, say so: `"entity_window_days": 90`. The default is 1 day, which strands a B2B deal that closes in month three. Widening buys reach, never trust — an entity match stays `candidate` and stays out of the billing-grade denominator at any window.

Two practical notes the shape of your app will raise. If the outcome legitimately lands more than 35 days after the work — a deal that closes in month three — **omit `occurred_at`**; the event is stamped at ingest and still binds at `exact`, because a shared-id join uses no time window at all. And wrap the call: recording an outcome must never break a working feature, so give it a timeout and swallow its failure.

### 3b. If the id changes later, say so

Work often starts under one identity and finishes under another — an anonymous chat session that becomes a known lead, a trial that converts, two CRM records merged:

```bash
curl -X POST "$GW/v1/alias" -H "x-vmx-key: $KEY" -H "content-type: application/json" \
  -d '{"from": {"session_id": "abc"}, "to": {"lead_id": "8172"}}'
```

Post it whenever you learn it, including long afterwards. Aliases resolve at *query* time, so nothing already captured is rewritten and the earlier spend re-joins the moment you assert the link. Without it that spend is orphaned: real money, real outcome, and nothing connecting them — so the unit cost silently omits the anonymous half of the story.

### 3c. Running an experiment (optional)

Declare the arms and let the gateway assign them:

```python
extra_headers={"x-vmx-experiment": "haiku-vs-opus",
               "x-vmx-variants": "control,haiku"}     # gateway picks; echoes the arm back
```

It hashes `(experiment, run id)` — so one unit stays in one arm across every call it makes — and returns the choice in the `x-vmx-variant` response header. Read it once per unit and serve that arm. You *can* set `x-vmx-variant` yourself and it always wins, but then the split is only as unbiased as your own logic: if it correlates with traffic source, time of day, or customer size, the experiment measures that rather than the model. Because the gateway never alters a request, it cannot switch the call it is already looking at — it decides the arm, you serve it.

Then `evaluate_switch` turns the arms into a verdict: cost per outcome on both sides, a non-inferiority test on the outcome rate, and what each confidence bar would cost in units per arm.

### 4. See it

Open `http://<backend>/?key=<your-key>`. The page leads with **cost per outcome**, each row carrying how much to trust it — the weakest binding tier behind it, whether the link was observed or inferred, and whether the cost is shared with another outcome. Below that, **unattributed spend** (work that reached no billing-grade outcome) is shown rather than dropped: a number that quietly omits it looks more complete than it is. Spend by model and agent follow as drill-downs, plus margin when outcomes carry `value`. Or query directly:

```bash
curl -X POST <backend>/run_metric -H "X-API-Key: <key>" -H "content-type: application/json" \
  -d '{"name":"cost_per_outcome","numerator":"total_cost_usd",
       "denominator":"verified_outcome_count","filters":{},"group_by":["outcome_name"]}'
```

### 5. Right-size your models (later, once you have real data)

With cost bound to outcomes over real traffic, `estimate_switch_cost` reprices your *actual observed token mix* against a candidate model — never a headline-rate ratio, never a fabricated zero for a model it cannot price. The eval layer goes further: it replays cheaper candidates against your captured workload and tells you whether one holds the same outcome — with the evidence, and **never switching automatically**. Because eval runs spend your provider tokens, it estimates the cost and gates on explicit approval first (`run_eval_funnel` → `approve_gate` → `get_recommendation`).

## What's in this repo

| Path | What it is |
|---|---|
| `gateway/` | the capture proxy — TypeScript, Cloudflare Worker shape, portable fetch/streams ([deploy notes](./gateway/README.md)) |
| `apps/server`, `apps/api` | the backend: ingest, attribution cascade, metrics, dashboard |
| `packages/` | the server-side engine: pricing, attribution (T1–T5), metrics DSL, evals, reconciliation, outcomes |
| `sdks/typescript` | published to npm: capture primitives + the in-process SDK |
| `sdks/python` | published to PyPI: the backend, its CLI, and the in-process SDK |
| `docs/onboarding/` | the agent-facing integration skill; `llms.txt` is generated |

### The published packages

Two packages ship from this repo, always at the same version.

```bash
pip install "valuemaxx[cli]"     # the backend + its CLI: valuemaxx up
npm install valuemaxx            # capture primitives, and the compat SDK
```

**`valuemaxx` on PyPI** is how you run the backend without Docker — `valuemaxx up`
serves the API and dashboard, and the published image bundles this same wheel.

**`valuemaxx` on npm** holds the capture primitives the gateway is built from: the
stream accumulators and usage extractors that get token counts right per provider
(Anthropic's `message_delta` *overwrites* rather than sums; OpenAI streams usage only
when `stream_options.include_usage` is set; Gemini's cached tokens are a subset of the
prompt count). If you are building your own capture path, this is the part worth
reusing rather than rewriting.

Both also carry an **in-process capture SDK** for hosts the gateway cannot sit in front
of: providers whose calls are SigV4/OAuth-signed (Bedrock, Vertex), teams who already
run an OTel collector (`POST /v1/traces` accepts standard OTLP), or anywhere proxied
egress is not an option. It instruments your client in place and ships spans to the
same backend, so the numbers and their honesty labels are identical either way.

## The honesty model

Three system axes ride every number and never get laundered upward (a rollup always shows the *least-trusted* of its parts):

| Axis | Values |
|---|---|
| **Cost provenance** | `measured` · `estimated` · `allocated` · `provider_reconciled` · `manual_reconciled` |
| **Binding tier** | `exact` · `deterministic` · `candidate` · `likely` |
| **Outcome signal class** | `action_attempted` · `outcome_confirmed` · `outcome_retracted` |

Binding tiers are decided by the server-side cascade, never by the caller; advisory tiers (`candidate`/`likely`) are excluded from billing-grade denominators and land in a review queue. Reconciliation to the invoice is **additive** (a new record, never an overwrite of the estimate); a retracted outcome is **removed from the cost-per-outcome denominator** and the metric re-emitted, never silently left.

## Self-hosting & data

Runs on a container + Postgres (`postgresql+asyncpg://…`), or embedded SQLite for local dev — `valuemaxx up` boots with zero configuration. Prompt/response **content is off by default**; it is only retained (self-host only) if you enable it for the eval/replay features, with a configurable TTL and an erasure path. Provider API keys pass through the gateway and are **never stored**; ingest keys and webhook secrets are never logged.

## Integrate with an AI coding agent (Claude Code / Cursor)

This project is built to be wired up **by** a coding agent. Point it at [`llms.txt`](./llms.txt) — the integration reduces to two shape-free questions the agent answers by reading your code: *where does the business fact become true?* and *what durable id is in scope there?* The onboarding skill in [`docs/onboarding/`](./docs/onboarding/) drives the full flow, including its approval gates (an agent never edits your production LLM path or names your outcomes without you confirming).

## Contributing

Contributions are welcome — start with [`CONTRIBUTING.md`](./CONTRIBUTING.md), which covers setup, the checks CI runs, and the two traps people hit here (generated files that must not be hand-edited, and the cross-language wire contract).

Engineering standards are strict and binding — see [`AGENTS.md`](./AGENTS.md): test-driven development (unit + integration + e2e), `pyright --strict` + `ruff`, ≥90% coverage on core, and a **ratchet** discipline (every bug becomes a permanent conformance rule so its class can't recur).

The rule underneath all of them: a change that makes a number *look* better by making it less honest is declined, even when the code is good.

## Project

| | |
|---|---|
| [Changelog](./CHANGELOG.md) | What changed, and which numbers were wrong before |
| [Contributing](./CONTRIBUTING.md) | Setup, checks, house style |
| [Security](./SECURITY.md) | Report privately — never a public issue |
| [Code of Conduct](./CODE_OF_CONDUCT.md) | Contributor Covenant 2.1 |
| [Releasing](./RELEASING.md) | Lockstep pip + npm from one `VERSION` |

## License

Apache-2.0 — see [`LICENSE`](./LICENSE).
