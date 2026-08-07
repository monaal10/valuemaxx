# valuemaxx

**stop tokenmaxxing. start valuemaxxing.** — *the anti-tokenmaxxing tool*

> **Know what each AI agent actually costs you — correctly — and what it earned, per outcome, with confidence.**
> For teams that **build** AI agents, not the ones who buy them.

Observability tools (Helicone, Langfuse) tell you what you **spent**. This tells you whether it was **worth it**: it captures *correct* LLM cost per unit of work, binds it to the real business outcome each unit produced — including outcomes that arrive days later, out of process — and labels every number with how trustworthy it is. Then it shows you, on your real workload, where a cheaper model holds the same outcome.

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

## Getting started (~5 minutes, ≤3 changed lines)

### 0. Run the two pieces

```bash
# the brain: FastAPI over SQLite (Postgres in prod), migrations on startup
docker run -p 8000:8000 -v vmx-data:/home/valuemaxx/data \
  ghcr.io/<owner>/valuemaxx-backend:latest
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

### 4. See it

Open `http://<backend>/?key=<your-key>` — spend by model/agent, cost per outcome at its confidence tier, margin when outcomes carry `value`. Or query directly:

```bash
curl -X POST <backend>/run_metric -H "X-API-Key: <key>" -H "content-type: application/json" \
  -d '{"name":"cost_per_outcome","numerator":"total_cost_usd",
       "denominator":"verified_outcome_count","filters":{},"group_by":["outcome_name"]}'
```

### 5. Right-size your models (later, once you have real data)

With cost bound to outcomes over real traffic, `estimate_switch_cost` reprices your *actual observed token mix* against a candidate model — never a headline-rate ratio, never a fabricated zero for a model it cannot price. The eval layer goes further: it replays cheaper candidates against your captured workload and tells you whether one holds the same outcome — with the evidence, and **never switching automatically**. Because eval runs spend your provider tokens, it estimates the cost and gates on explicit approval first (`run_eval_funnel` → `approve_gate` → `get_recommendation`).

## Known deployment constraint

A Worker on a `*.workers.dev` subdomain cannot `fetch()` a Cloudflare-proxied host — `api.anthropic.com` is one, and fails with error 1042 before the request leaves the edge (OpenAI/Gemini/OpenRouter are unaffected). Deploy the gateway on a custom domain, run it off Cloudflare, or route Anthropic via OpenRouter. Verify with one real call per provider you use; `/healthz` proves the worker booted, not that upstream is reachable. Details in [`gateway/README.md`](./gateway/README.md).

## What's in this repo

| Path | What it is |
|---|---|
| `gateway/` | the capture proxy (TypeScript, Cloudflare Worker shape, portable fetch/streams) |
| `apps/server`, `apps/api` | the backend: ingest, attribution cascade, metrics, dashboard |
| `packages/` | the server-side engine: pricing, attribution (T1–T5), metrics DSL, evals, reconciliation, outcomes |
| `sdks/typescript` | **the capture primitives the gateway is built from** + the compat SDK (below) |
| `sdks/python` | **the backend's distribution vehicle** (`pip install "valuemaxx[cli]"` → `valuemaxx up`) + the compat SDK (below) |
| `docs/onboarding/` | the agent-facing integration skill; `llms.txt` is generated |

### Are the npm/pip SDKs still needed?

**As the integration front door — no.** The gateway plus the outcome contract replace `init()`, run boundaries, outcome call sites, and flush plumbing. A host changes ≤3 lines and runs none of our code in its request path.

**As packages — yes, for three narrower jobs:**

1. `sdks/typescript` is the gateway's engine. The stream accumulators and usage extractors it imports encode already-paid-for bugs (Anthropic's `message_delta` *overwrites* rather than sums; OpenAI streams usage only when `stream_options.include_usage` is set; Gemini's cached tokens are a subset of the prompt count). A reimplementation would re-earn every one.
2. `sdks/python` ships the backend itself — `valuemaxx up`, the query CLI — and the Docker image bundles this wheel.
3. Both remain the **compat capture path** for hosts the gateway cannot serve: SigV4/OAuth-signed providers (Bedrock, Vertex), teams with an existing OTel collector (`POST /v1/traces` accepts standard OTLP), or a policy against proxied egress.

The SDK capture surface (`init()`, client patching, `run()`, baggage/injection carries) is no longer documented as the way in; it exists for the compat path and will slim over time.

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

Engineering standards are strict and binding — see [`AGENTS.md`](./AGENTS.md): test-driven development (unit + integration + e2e), `pyright --strict` + `ruff`, ≥90% coverage on core, and a **ratchet** discipline (every bug becomes a permanent conformance rule so its class can't recur).

## License

Apache-2.0 — see [`LICENSE`](./LICENSE).
