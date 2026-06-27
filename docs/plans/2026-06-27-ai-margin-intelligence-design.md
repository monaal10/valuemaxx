# Design: AI Margin Intelligence — cost-per-outcome with confidence, for teams that build AI

**Status:** Draft (pre-review)
**Date:** 2026-06-27
**Author:** monaal

---

## 0. One-liner

> **Know what each AI agent actually costs you — correctly — and what it earned, per outcome, with confidence.**
> For the people who *build* AI agents, not the ones who buy them.

Helicone/Langfuse tell you what you **spent**. We tell you whether it was **worth it** — and we start by getting the *cost itself* right (most homegrown COGS is wrong by 8–15%), then we deterministically bind that cost to the real business outcome each agent run produced — including outcomes that arrive days later, out of process — and tag every number with how trustworthy it is. We sit *on top of* the observability layer; we are the **accountability layer**.

**The moat, in order of defensibility:** (1) **correct, invoice-reconciled per-attempt COGS** — the credibility foundation; (2) **deterministic cost↔outcome binding** including the T3 round-trip that links delayed/out-of-process outcomes; (3) **the three honesty axes** that make every number auditable. The eval-backed model recommendation (§8) is an **evidence layer on top**, not the headline — because the outcome of an *un-run* model is counterfactual and can only be graded honestly (see §8.2).

---

## 1. Problem & ICP

### 1.1 The problem

Three questions companies building AI cannot answer today:
1. **Where is AI money going?** (cost attribution per agent/run/feature/customer)
2. **What did it earn?** (tie spend to the real business outcome — a resolution, a booked meeting, a closed deal, a merged PR)
3. **Could it be cheaper?** (would a cheaper/faster model produce the same *outcome*)

(1) is commoditizing (Helicone, Langfuse, LiteLLM, Datadog; the Linux Foundation "Tokenomics Foundation" launching 2026 will standardize it further). (2) is **unaddressed horizontally** — every incumbent stops at COGS and makes you supply the outcome number. (3) is lightly occupied but the *exact* framing "eval-backed swap recommendation on YOUR real outcomes" is a gap.

### 1.2 ICP — "AI builders, not AI buyers"

The customer is **whoever makes the API call and books the token as COGS.** If the token spend lands on their bill, they're a prospect; if it lands on a vendor's bill, the vendor is the prospect.

**Beachhead (lead here):** AI-native / agentic vendors selling outcome-priced products (support, SDR, etc.) — Decagon/Sierra/Intercom-Fin-class + the funded long tail. For them:
- tokens *are* their literal COGS;
- they price per outcome (per resolution), so **cost-per-outcome is existential margin math, not a dashboard nicety**;
- they own **both** sides (the agent and the outcome event), so the join is a deterministic ID match — the hard connector/identity problem *collapses to config*.

**Expansion (the house):** startups building agents (to sell or for themselves), solo devs building agents for themselves, then SaaS embedding AI features, then regulated builders. The broad ICP has the cross-system identity problem the connector + inference layer solves later.

### 1.3 The dead zone (stated honestly)

Pure **buyers** running zero inference have no cost side — not our customer. The buy-trend doesn't shrink the market; it **concentrates** token spend into fewer, larger, more margin-desperate accounts (the vendors). We sell to the builders.

### 1.4 The honest existential threat

If OpenAI/Anthropic/Google ship managed agent platforms with built-in cost-per-outcome telemetry, the **cost layer commoditizes**. Defense: the moat is **not** cost capture — it is **correct reconciled COGS + deterministic cost↔outcome binding (incl. delayed outcomes) + the honesty axes, over the customer's own messy data**, which platforms won't own. This is a **per-customer moat** (each customer's own joined cost+outcome history is the asset), **not** a cross-customer network effect — stated plainly so we don't overclaim defensibility. Build the intelligence; treat cost-capture mechanics as table stakes, correctness as the edge.

---

## 2. Positioning

- **Broad / OSS line:** "Cost-per-outcome with confidence — for teams that build AI, not buy it."
- **Beachhead / sales line:** "Gross margin per resolution for outcome-priced AI agents — correct COGS (not a notebook), with model-swap recommendations to protect margin."
- **Lead with correctness** (their homegrown COGS is commonly wrong by 8–15%) **and action** (model routing). **Never lead with "the join is trivial"** — a technical buyer hears that and builds it themselves.
- **OSS / self-host is strategic, not cosmetic:** these vendors process their customers' PII, so SaaS-that-ships-prompts is a compliance blocker. Self-host is *gating* to land enterprise logos. Open-core: give away ingestion; monetize the shared-COGS allocation model, eval-backed routing, and board-grade margin reporting.

---

## 3. The engine (architecture overview)

One pipeline, a typed spine, three honesty axes. Every stage is a read or write over the same joined data.

```
  COST SIDE                                OUTCOME SIDE
  init() auto-instrument (Py + TS)         declared outcomes captured via
   → correct, reconciled CostEvents         instrumentation we already run
   per run_id (the §5 work)                 + onboarding agent (the §6/§7 work)
        │                                          │
        └──────────────► JOIN / BINDING ◄──────────┘
              (exact → deterministic → entity → inferred cascade,
               every binding labeled with a confidence tier)
                          │
            every run now carries: cost (provenance-tagged)
                       + outcome (signal-classed) + binding (tier)
                          │
        ┌─────────────────┼──────────────────────┐
        ▼                 ▼                        ▼
   user-defined       margin / ROI            EVAL-BACKED MODEL
   metrics            rollups                 RECOMMENDATION (§8, evidence
   (grammar)          (cost-per-outcome)       layer — not the headline)
                                               "cheaper model holds parity on
                                                the best available, honestly-
                                                labeled ground-truth rung"
```

**Headline = the left/center of this diagram** (correct reconciled COGS + deterministic outcome binding + the honesty axes). The eval recommendation (right) is an evidence layer that consumes the joined data; it is deliberately *not* positioned as the differentiator (see §8.2 for why the "holds your real outcome" claim cannot be made honestly for counterfactual/delayed outcomes).

### 3.1 The three honesty axes (system-owned, never user-settable, surfaced everywhere)

**Exactly THREE system honesty axes** (the eval `reliable`/`directional` grade is a per-recommendation label local to §8, **not** a fourth system axis — it does not ride every event, so it is not in this table or the conformance invariants):

| Axis | Values | On |
|---|---|---|
| **Cost provenance** | `measured` / `estimated` / `allocated` / `provider_reconciled` / `manual_reconciled` | every cost number |
| **Binding tier** | `exact` / `deterministic` / `candidate` / `likely` | every outcome→run link |
| **Outcome signal class** | `action_attempted` / `outcome_confirmed` / `outcome_retracted` | every outcome event |

**Conservative propagation (H7):** every rollup output carries **both** a `minimum_tier` (the least-trusted member tier — the headline label a surface must show) **and** a `confidence_distribution: dict[tier, int]` (so no surface can silently collapse "1 exact + 50 candidate" into a clean number). **Both fields are part of the `core` rollup model and are serialized on the wire/storage schema** — the API response model and the `notify/` digest model both *require* them (a conformance rule fails any rollup-returning capability whose output schema omits them), so they cannot be dropped at the projection boundary. You can never make a number look more certain by aggregating it.

**How the axes compose:** a margin number combines a cost (provenance axis) and an outcome (binding + signal axes); its displayed confidence is the *minimum* across all contributing axes, mapped to a single user-facing label (`high` = all `provider_reconciled`/`measured` + `exact`/`deterministic` + `outcome_confirmed`; `medium` = any `candidate`/`allocated`; `low`/`advisory` = any `likely`/`estimated` or `directional` eval). `notify/` digests MUST include the `minimum_tier` label on every metric.

**Retraction (H8):** an `outcome_confirmed` may later flip to `outcome_retracted` (a resolved ticket reopens weeks later). Retracted outcomes are **removed from the cost-per-outcome denominator** and the historical metric is annotated and re-emitted — never silently left to inflate the denominator. Already-sent digests referencing a now-retracted outcome are corrected on the next cycle.

This consistency *is* the credibility moat — and per §1.4 it's a **per-customer** moat (their own outcome history), not a cross-customer network effect.

### 3.2 Authentication, tenancy & isolation (C2)

- **Tenant model.** `tenant_id: UUID` is a **required, non-nullable** `core`-level field (no default) on **every** event (`CostEvent`, `OutcomeEvent`, `AttributionResult`, `Run`) — enforced at the pydantic boundary so an untenanted event cannot be constructed. A "tenant" is one isolated customer account.
- **Self-host = single-tenant per deployment** (the common case for the beachhead — collapses most multi-tenancy concerns), **but ingest auth is still required** so a deployment doesn't accept anonymous telemetry.
- **`init()` credential.** The SDK presents a **per-tenant ingest key** (a write-scoped token) to the OTLP/HTTP ingest endpoint. Keys are issued/rotated via the API.
- **API/MCP/CLI authn.** Per-tenant API key or JWT; every capability handler is tenant-scoped.
- **Store isolation.** v1 = row-level `tenant_id` filter. **Every repository interface method takes `tenant_id` as a mandatory first parameter** (not an optional filter) — there is no API to query without a tenant scope, so isolation is structural, not disciplinary. A **conformance rule** asserts no store query path omits the tenant scope. Multi-tenant SaaS hardening (Postgres RLS/separate schemas) is a later, documented step.
- **Webhook ingest** (outcome receivers) authenticate via signed-secret verification per source, plus the tenant ingest key.

---

## 4. Monorepo layout & the single-source-of-truth principle

Python monorepo (uv workspace). Logic packages never know about HTTP/MCP/CLI; surfaces are projections of one capability registry. TS SDK is a thin producer over the same OTLP wire contract.

```
antitokenmaxxing/
├── packages/
│   ├── core/             # THE typed spine — pydantic v2 models, imported by all.
│   │                     #   Run, CostEvent, OutcomeEvent, AttributionResult,
│   │                     #   Confidence, Provenance, MetricDefinition, AllocationRule
│   ├── capabilities/     # ★ single source of truth for every operation:
│   │                     #   @capability(input, output, handler, description, examples)
│   │                     #   + the registry every surface projects from
│   ├── capture/          # cost capture: pluggable CostSource strategies
│   │   ├── client_instrument/   # Python wrapt monkeypatch of openai/anthropic
│   │   ├── otlp_ingest/         # language-agnostic OTLP-in (TS, any lang)
│   │   ├── provider_costapi/    # reconciliation true-up (authoritative)
│   │   └── gateway/             # OpenRouter (authoritative inline); NOT Cloudflare AIG
│   ├── outcomes/         # declarative outcome rules + capture seams
│   │   ├── instrument/          # wrapt patch of declared functions/HTTP/ORM
│   │   ├── rules/               # outcomes.yaml schema + evaluator
│   │   └── ingest/              # webhook/event ingest for external outcomes
│   ├── attribution/      # the binding cascade (exact→deterministic→entity→inferred)
│   │   ├── binding/             # contextvars / baggage / roundtrip-id / entity match
│   │   ├── inference/           # the semantic matcher (LAST tier, labeled)
│   │   └── confidence/          # system-owned tier scoring
│   ├── reconciliation/   # estimate→provider-Cost-API true-up; ReconciliationRecord
│   ├── allocation/       # shared-COGS allocation (tiered, transparent)
│   ├── metrics/          # user-defined metric grammar → query
│   ├── eval/             # eval-backed model recommendation (the headline)
│   │   ├── discover/            # cluster calls into agents/prompts (Drain, etc.)
│   │   ├── dataset/             # eval-set from traces + EvalGen rubric
│   │   ├── search/              # successive-halving model search
│   │   ├── grade/               # ground-truth: outcome-label / human / judge
│   │   └── report/              # recommendation artifact (md+json)
│   ├── onboarding/       # the onboarding agent: scan→propose→wire→validate
│   └── store/            # configurable storage port (SQLite local / Postgres prod)
├── apps/
│   ├── api/              # FastAPI — iterates registry → routes (thin projection)
│   ├── mcp/              # MCP server — iterates registry → tools (thin projection)
│   ├── cli/              # CLI — iterates registry → commands (thin projection)
│   └── notify/           # Slack/email digest sinks (read via capabilities)
├── sdks/
│   ├── python/           # the init() SDK (thin producer → OTLP)
│   └── typescript/       # the init() SDK (thin producer → OTLP)
├── clients/             # typed SDKs generated from the registry JSON Schema
├── AGENTS.md  CLAUDE.md  # engineering standards (see separate docs)
└── (uv, ruff, pyright, pytest, CI)
```

**Enforced invariants & dependency directions (H6):**
1. **`core` is the only place types are defined** — including **repository interfaces** (`RunRepository`, `CostEventRepository`, …) as abstract base classes. `store` contains only concrete impls (Postgres now; a separate `store_clickhouse` package later); `apps/*` inject the impl at startup. Logic packages depend on the *interface* in `core`, never on a concrete store. → structural no-duplication.
2. **`capabilities` is a thin registry** — it exposes only `Registry` + `@capability` and **imports no logic package**. Each logic package depends on `capabilities` and exposes `register(registry)`; `apps/*` call `discover_and_register(...)` (push registration, so `capabilities` never becomes a god-module). `onboarding` imports `capabilities`, never the reverse.
3. **`apps/*` are dumb projections** — but a capability declares which surfaces it supports (H5): `@capability(..., surfaces={api, mcp, cli}, mode=request_response | streaming | async_job | webhook_inbound)`. The CI test asserts **"every capability appears on every surface it declares."** Streaming ingest, long-running eval (`async_job` → `job_id` + `status_poll` pattern), and webhook receivers declare narrower surface sets rather than being force-fit into request/response. No circular package deps (import-linter contract in CI).

---

## 5. Cost capture & reconciliation (the credibility foundation)

Thesis: *"your COGS is commonly wrong by 8–15%; ours isn't"* — earned by capturing the structured usage object per HTTP attempt, pricing each token class correctly, and truing up to the provider invoice.

### 5.1 Integration (one-line-or-less, Python + TS from day one)

- **Python:** `import yourtool; yourtool.init()` — patches the **HTTP transport layer** (`httpx.Client.send` / `AsyncClient.send`, used by both `openai` and `anthropic` SDKs) plus the public client methods, via `wrapt`. This catches LangChain/LlamaIndex/CrewAI **because they call these clients underneath** — but see the propagation caveat below; "for free" is true for *cost capture*, qualified for *attribution*.
- **TS:** `init()` is **real instrumentation work, not a shim** (H1). The OpenAI/Anthropic Node SDKs do *not* natively emit OTel spans. The TS SDK registers OTel auto-instrumentation for the OpenAI/Anthropic Node clients (via `@opentelemetry/instrumentation-*` / OpenLLMetry or a purpose-built monkey-patch) and installs an OTLP exporter; for the **Vercel AI SDK** it injects the tracer via `experimental_telemetry`. **Streaming cost accumulation in TS is explicitly designed** — accumulate tokens across chunks before emitting the cost span. "No parallel JS universe" is the *goal* (shared OTLP wire format), not a free pre-existing emission.
- **Universal path:** OTLP-in for any language.
- **`init` scaffolder** detects framework (FastAPI/Django/Next/Express/LangChain) and injects setup minimally + reversibly → agent-integratable.

**Context-propagation gaps (H2 — must be handled, not assumed).** `run_id` rides `contextvars`. `asyncio` tasks and `asyncio.to_thread` propagate context; **raw `ThreadPoolExecutor.submit()` and `os.fork`/multiprocessing do NOT** (PEP 567), and LangChain `RunnableParallel`/CrewAI dispatch through thread pools. So `init()` **patches `ThreadPoolExecutor.submit` to wrap callables in `copy_context().run(...)`** (the approach the OTel Python SDK uses). **Fork/multiprocessing boundary:** a child process starts with **no** ambient `run_id` (contextvars don't cross `fork`/`spawn`); the SDK does **not** guess — it requires the run context to be re-established explicitly in the child (a documented `with track.run(run_id=...)`), and any LLM call in a child without it is captured with binding tier downgraded (T1 unavailable → T2/T4) and **labeled**, never silently mis-bound. T1 = `exact` *only when context propagated*.

**SDK failure modes (H9 — an instrumentation lib that throws into `create()` is an adoption-killer).**
- **Fails open, always.** Internal SDK exceptions are caught-and-logged, **never** propagated into the customer's call path.
- **Ingest-unavailable** → fire-and-forget with a bounded in-memory queue; events past the bound are dropped and **counted** (a dropped-event counter is itself reported), never block the host.
- **Overhead bound:** the wrapper is non-blocking and targets `<1ms` added latency on the call path; cost computation and emission happen off-path.
- **Self-test on startup:** `init()` verifies the patch took effect and **warns loudly if ineffective** (e.g. an incompatible SDK version) — never silently captures nothing.
- **Reversible scaffolding** = the `init` scaffolder's edits are removable without touching app logic (a single import + call site).

### 5.2 Capture correctness (kills the 8–15% leak)

- **One `CostEvent` = one HTTP attempt** where the mechanism allows it (H3): per-attempt visibility requires patching the **transport layer** (`httpx.send` / SDK internal `_request`) — retries live in `_base_client`/`httpx`, *below* the public `create()`. **Version detection + self-test:** at `init()` the SDK checks the installed `openai`/`anthropic`/`httpx` versions against a known-compatible range and runs a no-op patch self-test; if the transport hook is absent or the version is outside the tested range, it **gracefully degrades to per-call** capture tagged `capture_granularity: per_call` and **logs a warning naming the version** — never silently captures the wrong granularity. Where the hook is present we tag `capture_granularity: per_attempt`.
- **Streaming:** force `stream_options.include_usage` (OpenAI); use SDK accumulators (`get_final_message()`) for Anthropic; **never sum `message_delta` usage** — the cache-token fields appear in *both* `message_start` and `message_delta`, and summing them (instead of taking terminal values) is the `@langchain/anthropic` 2× cache double-count bug; `get_final_message()` fixes it by taking terminal values. Cancelled stream → recover partial, else flag `partial_recovered`; never silently log zero.
- **Token vector always split by class** (internal `CostEvent` schema): `input_uncached / cache_read / cache_write_5m / cache_write_1h / output / reasoning`. The 5m/1h split comes from nested `usage.cache_creation.{ephemeral_5m,ephemeral_1h}_input_tokens` (not flat fields); `reasoning` is **derived** (not a distinct `usage` field — count `type:"thinking"` blocks), embedded within `output`. OpenAI prompt-caching has a cache-read discount but **no explicit cache-write cost** — pricing is provider-specific, mapped per provider. Blending the input classes mis-prices the cached slice badly.
- **`tiktoken` banned for cost** (undercounts Claude up to ~12% for typical content, varies by content type); last-resort flagged fallback only.
- **Six enforced invariants** (e.g. `cache_read + cache_write ≤ total_input`; `output ⊇ reasoning`; provider-specific cache formula) — violation logs a `provenance_warning`, never silent.
- **Idempotency (M7):** `CostEvent` dedup key = `(run_id, attempt_id)`; `OutcomeEvent` dedup key = `correlation_id` (or `(source, external_id)`). Ingest is at-least-once (OTLP + webhook retries), so the store **upserts on conflict** — double-delivery never double-counts.

### 5.3 Reconciliation (estimate → invoice true-up)

- **Per-request billed cost is impossible by construction** — providers expose only `day × project × line-item` (OpenAI Costs API `1d`-only; Anthropic `cost_report` `1d`-only, `usage_report/messages` supports `1m`/`1h`/`1d`). Both Anthropic endpoints require an **Admin API key** (`sk-ant-admin01-`) + org account; **Bedrock/Vertex/Azure-hosted models are not in these provider Cost APIs** — reconcile those against the cloud bill (CUR/GCP/Azure) or a manual CSV upload tagged `manual_reconciled`. The `CostSource`/reconciliation adapter accommodates both automated-API and manual-upload paths. So reconciliation is an **aggregate true-up, prorated** back to requests.
- Sum estimates per match-key `(provider, project/workspace, model, token-class, day)`, fetch billed total, compute `proration_factor` so per-request reconciled values sum *exactly* to the authoritative daily total.
- **Immutable estimate + additive `ReconciliationRecord` delta** — never UPDATE the estimate. Re-reconcile a trailing 2–3 day window (buckets provisional).
- Drift <10% = rounding noise; >10% = real miscount → alert with ranked cause (cache mispricing, negotiated rate, batch discount, credits, tax). Typical drift 0.5–3%.
- **Honest bound on the pitch:** we claim "correct, complete, invoice-reconciled COGS with labeled residuals" — **not** "exact per-call billed cost." Per-request reconciliation is `prorated_from_bucket`, labeled.

### 5.4 Shared-COGS allocation (tokens are only ~37% of true AI cost)

Three-tier model, every line labeled `measured` vs `allocated`:
- **Tier 1 DIRECT (measured):** tokens + embeddings + reranking + per-query vector-DB + metered media + paid tool calls + retry tokens.
- **Tier 2 SHARED-PROPORTIONAL (allocated by declared key):** GPU productive-seconds, vector-DB ÷ queries, fine-tune amortized over inferences, egress by bytes.
- **Tier 3 FIXED OVERHEAD:** idle GPU **quarantined and reported beside** the unit cost (CloudZero 75%-utilization pattern), never smeared in.
- Every allocated line carries `allocation_key`, `confidence`, `sensitivity_pct`, `rule_version`. The rollup surfaces **`pct_unallocated`** as the honesty anchor. Report **cost per *verified* resolution** (fully-loaded ÷ verified outcomes).
- **Intake (M6):** Tier-2/3 inputs (GPU productive-seconds, fine-tune amortization, vector-DB cost, monthly bills) are operator-supplied via a `shared_costs.yaml` (analogous to `outcomes.yaml`; the onboarding agent proposes it). **When absent, we publish Tier-1 (measured) only and surface `pct_unallocated` prominently** — never silently report a partial number as complete.

### 5.3a Query semantics over mixed reconciliation states (M3)

A time-range query (e.g. `last_7_days`) can span days that are `provider_reconciled`, `provisional`, and `estimate_only`. Rule: per-row provenance is preserved; aggregates carry a **`provenance_breakdown`** (how much of the total is reconciled vs estimated). After a **>10% drift alert**, we keep publishing the figure tagged `estimated` **with the warning attached**, and annotate/retract any already-emailed digest on the next cycle — we never silently swap a number or hide that it's provisional.

### 5.5 Cost sources (pluggable, honesty-gated)

- `client_instrument` (Python), `otlp_ingest` (universal/TS), `provider_costapi` (authoritative reconciliation), **`gateway:openrouter`** (authoritative inline `usage.cost`, no markup; `user` field carries attribution).
- **Design law:** *we only take a cost source that yields authoritative billed cost or properly-reconciled actuals. We never ship vendor-estimated cost as a spend source.* → **Cloudflare AI Gateway dropped** (estimate by its own docs).

---

## 6. Outcome capture (near-zero human code)

The contradiction resolved: **capture is explicit instrumentation (reliable, reaches plain functions and delayed/out-of-process outcomes), but the *authoring* is done by the onboarding agent reading the codebase.** The human reviews a proposed diff once.

### 6.1 Declarative outcome rules (`outcomes.yaml`)

User (via onboarding agent) declares an outcome **once** as: `match` (function path / HTTP call / DB-ORM write / status transition / webhook) + `when` predicate + `value` + `bind` + `signal`. At `init()` the SDK reads the config and:
- in-process matches → live `wrapt` monkeypatches of the named functions (covers all call sites; no per-call-site edits);
- external matches → connector/webhook path.

```yaml
outcomes:
  - name: loan_funded
    match: { function: "myapp.loans.update_loan_status", when: "args.status == 'funded'" }
    value: "args.amount"
    bind:  { entity_key: "args.application_id" }
    signal: outcome_confirmed

  # T3 (H4): run_id round-trip injection is DECLARATIVELY CONFIGURED, not magic.
  # The onboarding agent proposes this block; the user reviews it.
  - name: payment_succeeded
    match: { webhook: stripe, event: "payment_intent.succeeded" }
    run_id_injection:
      sdk_call:    "stripe.PaymentIntent.create"   # where we stamp run_id (auto-wrapped)
      inject_into: "metadata.run_id"               # the passthrough field on the object
      webhook_event: "payment_intent.succeeded"    # the echo event
      extract_from:  "data.object.metadata.run_id" # where it comes back
    value: "data.object.amount"
    signal: outcome_confirmed
```

**T3 injection mechanism (H4 — design-level, not deferred to impl).** The `packages/outcomes/instrument/` package owns it: at `init()`, after reading `outcomes.yaml`, it `wrapt`-wraps each declared `run_id_injection.sdk_call` (e.g. `stripe.PaymentIntent.create`) so the wrapper reads the active `run_id` from `contextvars` and merges it into the configured `inject_into` path (`metadata.run_id`) of the outbound call's kwargs. **Init-ordering:** injection wrappers must be installed before the host app issues the call; if the target symbol isn't importable at `init()` (lazy import, wrong order), `init()` emits a **startup warning** naming the unresolved `sdk_call` — never silently no-ops. The webhook receiver then reads `extract_from` to recover `run_id`.

**T3 coverage limit (H4/M1-arch):** round-trip injection only works where the external system **echoes arbitrary metadata** on its webhook (Stripe, HubSpot custom properties, Zendesk custom fields do; Salesforce outbound messages and several CRM webhooks do **not**). When echo is unavailable, the outcome falls through to **T4 entity-match** (which is therefore **in Phase 1** as the T3-webhook fallback — see §12), labeled accordingly, never silently mis-bound.

### 6.2 What we capture per outcome (to make it attributable)

`OutcomeEvent { name, signal_class, value, occurred_at, binding{run_id, tier, bound_by}, entity_keys, correlation_id, source, raw }`. Attributability lives in `binding` + `entity_keys`.

### 6.3 The binding cascade (determinism first, inference last)

| Tier | Mechanism | Confidence |
|---|---|---|
| **T1 ambient context** | read `run_id` off `contextvars` when the fn fires (in-process) | `exact` |
| **T2 session/baggage** | `run_id` rides W3C baggage across live service hops | `exact` |
| **T3 round-tripped id** | **declaratively-configured `run_id` injection** into the agent's outbound object (Stripe metadata, ticket custom field) via the `run_id_injection` block (§6.1) — zero-code-per-callsite, the onboarding agent proposes it; the later webhook **echoes it back** → binds delayed/out-of-process outcomes deterministically. Works only where the system echoes metadata. | `deterministic` |
| **T4 entity match** | shared `customer_id`/`order_id`, tie-broken by time window | `candidate` |
| **T5 semantic inference** | LLM-judge over entity + time + content; review-queued, never fed to billing-grade metrics | `likely` |

**T3 is the technical heart** — it converts "impossible delayed attribution" into an exact join by stamping a durable ID into the external object so it round-trips. The semantic matcher (T5) is the **labeled last resort** for outcomes that happen entirely in an external UI with no shared ID — most relevant to the *broad* ICP, rarely needed for the beachhead.

### 6.4 Honesty primitives

- `action_attempted` vs `outcome_confirmed` — a successful tool call/HTTP 200 ≠ business success (METR: ~half of test-passing PRs wouldn't merge). Only authoritative results are confirmed.
- **Outcomes support late mutation/retraction** — a "resolved" ticket can flip weeks later (Langfuse attach-a-score-30-days-later model).

---

## 7. The onboarding agent (a core component)

Runs as a Skill the user's coding agent executes (or our MCP flow) after install + keys. Mission: make the codebase produce attributable OutcomeEvents with near-zero human effort.

1. **Scan & discover** — agent run boundaries (where `init()` goes), candidate outcome points (status setters, `mark_*`, ORM saves, outbound Stripe/CRM/calendar/email calls, webhook handlers), durable entity IDs in scope.
2. **Propose** — a reviewable summary of found outcomes + entity IDs + which can be made deterministic vs which will be candidate/likely. **The human's only effort: review/edit.**
3. **Generate wiring (hybrid, agent-chooses per outcome):** in-process → declarative rule; delayed/external → explicit captured line in the webhook handler + T3 `run_id` injection at the external-write site; entity-ID capture at run entry.
4. **Validate** — call MCP `validate_*` tools; dry-run against recent traffic to preview `cost-per-<outcome>`.
5. **Hand off as a reviewable diff/PR** — explicit, version-controlled, nothing silent.

**Execution context & repo access (H12).** Default: the agent runs **in-process locally** as a Skill the user's own coding agent (Claude Code/Cursor) executes, using the user's *existing* git/editor auth — source never leaves their machine, and *their* identity opens the PR. An optional server-side mode uses a GitHub App scoped to **`contents: read` + `pull_requests: write` only** (no direct push, no admin); it is opt-in because the scan reads source that may contain secrets. The "emits diff not source" guarantee is **enforced mechanically**, not by intent: the server-side agent's toolset is read-only over the repo and its only write path is the bounded PR-branch diff — it has no tool that can transmit raw file contents off-box. Secrets encountered during the scan are never echoed into the proposed diff or logs.

Reuses the agent-integratability machinery: shipped Skill + Cursor rules, MCP `validate_*`/`scaffold_*` tools, precise types + per-framework `examples/`, and an `llms.txt` with an `instructions:` section (corrects model priors on our brand-new API). `init` writes an `AGENTS.md` snippet into the *user's* repo (agents don't scan `site-packages`).

---

## 8. Eval-backed model recommendation (an evidence layer — NOT the headline)

**Why not the headline (C1):** the outcome of the *un-run* (cheaper) model is **counterfactual** — you never observe whether the road-not-taken would have resolved the ticket or closed the deal. So "the cheaper model holds your *real* outcome" cannot be claimed honestly for open-ended/delayed outcomes (most beachhead value). Outcome-as-label is only valid where **output deterministically reconstructs the outcome** (classification, extraction, deterministic resolution); otherwise the grader honestly falls back to a labeled proxy (LLM-judge / reference), **capped at `directional`**. The headline moat is §5 (reconciled COGS) + §6 (deterministic binding) + §3.1 (honesty axes). This section is the *evidence layer* that sits on the joined data.

Revised claim: *"on your real workload, this cheaper/faster model holds parity on the best available, honestly-labeled ground-truth rung — here's the evidence and the confidence, your call."* Funnel: discover → ground-truth → eval-set → search → cost-gate → recommend → re-run.

### 8.1 Discover agents + prompts
Deterministic backbone first (70–90% free): `GROUP BY` over call-site identity (`gen_ai.agent.name`), **tool-set fingerprint** (hash of sorted tool names), prompt-registry template IDs. Templatize residue with **Drain** (hash the *skeleton*, not the filled string). Embedding-clustering (UMAP→HDBSCAN→LLM-label) only for unstructured apps. Task-type detected structurally. **Auto-ship** cluster boundaries/skeletons; **human-confirm** names/merges/the eval criterion via the onboarding agent.

### 8.2 Ground truth / "at parity" — the ground-truth rungs, honestly labeled
Ranked rungs (the eval uses the highest available **and labels which**): **`outcome-label` (real captured outcome) > human-labeled subset > validated LLM-judge > reference (current-model output, pre-filter only).**
- **`outcome-label` is valid ONLY where output deterministically reconstructs the outcome** (classification, extraction, deterministic resolution) — there, "would the cheaper model's output also have resolved?" is answerable from the output alone. **For counterfactual/delayed/open-ended outcomes (support resolution, SDR meetings, closed deals) it is NOT answerable** — the grader drops to `judge`/`reference` and the recommendation is **capped at `directional`**, and the artifact says so. This honesty is the difference between us and a tool that silently calls judge-agreement "outcome parity."
- **Human-labeled ground truth on a stratified subset is non-negotiable** even when everything else is automated — every automated layer can be systematically wrong in a correlated way. Judges validated against human labels (TPR/TNR ≥ 0.9) or capped at `directional`.
- The recommendation artifact (§8.6) always records the **`label_source` rung used** and the resulting `reliable`/`directional` grade.

### 8.3 Eval set
Use existing user evals if present. Else eval-generation agent builds a **stratified dataset from real traces** (frequent + long-tail + adversarial + failure; oversample outcome-bound), rubric via the **EvalGen** human-alignment loop. Versioned, `source_trace_id` back-links. Living artifact (sets decay).

### 8.4 Smart model search (not 100 models)
**Prune 100 → 3–8 for $0** (task-matched leaderboards, drop Pareto-dominated models, task-type fit, own logs). **Successive halving:** smoke-eval all on ~30–50 cases → eliminate clear losers → escalate 2–3 survivors to 200–500 cases → winner only when 95% CIs separate. **Smoke-stage threshold (M4):** n=30–50 cannot separate 95% CIs for small deltas, so the smoke stage drops models underperforming the incumbent by **>25% (no CI requirement)**; the **CI requirement applies only to the final recommendation** on the confirmation set. Present a **cost × quality × latency Pareto frontier.** Switch wholesale if uniform parity; route only if bimodal difficulty. OSS models included but **costed fully-loaded** (GPU+ops ÷ real volume — "free per token" is often the most expensive point at low volume).

### 8.5 Cost-gating (BYO-keys — the estimate IS the consent)
Count input tokens exactly per candidate with the provider's own tokenizer (Claude: free `count_tokens`, rate-limited by tier; never reuse counts across model *generations* — the Opus-4.7/4.8/Fable-5 tokenizer family runs ~1–1.35× higher than older Claude tokenizers, a cross-generation delta distinct from tiktoken error; never `tiktoken` for Claude). Output tokens via **sample-first (run 5%, measure, extrapolate)**.

**Two-phase gate (M2)** — true full-run cost is only knowable after smoke-eval reveals survivors:
1. **Phase 1:** gate the *smoke-eval* cost up front (exact per-candidate `~$X` table) — one approval.
2. **Phase 2:** after survivors are known, show the *projected full-run* cost on the confirmation set — **second approval** before the expensive stage.
Gate controls: auto-approve under a small ceiling; manual above; mandatory 5% canary; hard budget caps that refuse to start if `est > budget`; surface *whose* key and *which* provider.

**BYO provider-key handling (C3) — a hard requirement, not an afterthought.** Provider keys are plaintext secrets; storing customers' keys in SaaS is the same compliance hazard as shipping their prompts (§2). The model:
- **Default / self-host:** keys are **never persisted** — supplied per eval run (env/secret-ref), held in memory only for that run's duration, then dropped from process state (best-effort zeroization of the buffer; reference released immediately). Keys are **never logged and never returned by any read API** (a conformance rule asserts no key field reaches a logger or a response model). The env-var path is documented as the operator's responsibility to scope.
- **SaaS (if ever offered):** keys **must not be at rest in plaintext** — encrypted with a per-tenant envelope key (KMS), or referenced by ARN from the user's own secrets manager. Transport is TLS-only; rotation supported; keys are never logged, never returned by any read API.

### 8.6 Recommendation artifact
Diffable **JSON (source of truth) + Markdown/PR view**: parity score **with 95% CI** (we add the significance layer Promptfoo/Braintrust don't), cost delta + projected $/month at real volume, latency p50/p95/p99, **sample disagreements** (where cheaper model differed — the trust-builder), gap distribution across cohorts, full methodology (pinned snapshots, shared prompt, label source). **Confidence-labeled** (`reliable`/`directional`). **Never auto-switches** — evidence for a human decision; promotion is human → canary → auto-rollback.

### 8.7 Cadence
Triggered, never on a timer: **new-model release** (watch provider feeds, canary `latest` vs golden set), cost/latency drift, new discovered agents. **Switching hysteresis** (require ≥15–20% improvement) prevents churning on noise.

---

## 9. Storage & tracing

- **Configurable storage behind a port.** Default local = **SQLite** (zero infra, ships with Python). Default prod = **Postgres** (joins, JSONB for raw records). Scale tier = **ClickHouse** — *designed-for, not built now* (earns its place only at 1–5M events/day; the port keeps the door open). One Postgres implementation now.
- **Raw record JSON** kept (Postgres JSONB / local dir) for the inference-matching step and **replay** (re-run matching after logic improvements). Match-keys indexed.
- **Tracing: OTel-native + minimal built-in viewer.** Depend only on **Apache-2.0** SDKs (OpenTelemetry, OpenLLMetry, OpenInference). **Integrate-don't-vendor** Phoenix (ELv2), Langfuse (MIT but heavy); **never link** Tempo (AGPL). Jaeger is the clean BYO backend. Trace + cost are the same OTLP stream, fanned out.
- **Cloudflare:** AI Gateway dropped (estimate-only). Cloudflare hosting = optional edge-ingestion adapter only, never the OSS core (lock-in: D1/DO/Workers have no off-Cloudflare equivalent).

### 9.1 Content retention & data handling (H10 — resolves the "content off by default" vs "eval/replay needs content" tension)

- **Cost capture needs NO content** — token counts + metadata only. Content (prompt/response) is **off by default**.
- **Eval (§8) and raw-record replay (§9) require stored trace content**, which for a support-agent beachhead trivially contains end-user PII. Therefore: **content retention is a self-host-only, opt-in setting.** Eval that needs `source_trace_id` content prompts the operator to enable retention; if absent, eval runs on the metadata/structured subset only and says so. Content does not leave the customer environment in self-host.
- **PII policy:** `OutcomeEvent.raw`, prompt/response fields, and entity keys may carry PII — they are flagged, hashable (email→HMAC), and subject to retention.
- **Default retention TTL per record type** (e.g. raw content 30d, structured events 1y — configurable) + a **GDPR/CCPA erasure mechanism** (delete-by-entity/tenant). Self-host shifts the compliance obligation to the operator — stated as such.
- **`notify/` digests carry aggregate metrics + `minimum_tier` only** — never raw prompts, never end-user identifiers.

---

## 10. Connectors (for external outcomes / broad-ICP expansion)

Not needed for the beachhead (outcomes are in-process). For external outcomes and the broad ICP:
- **No single OSS connector product does this** (Supaglue acqui-hired by Stripe 2024; the survivors have mixed licenses — Airbyte core is BUSL, RudderStack has Apache-2.0 components, Nango is permissive — none is a clean turnkey OSI-open fit). The winning pattern: **embed `dlt` (Apache-2.0) behind a thin `SourcePort`** (the PostHog pattern) — preserves the full raw record as JSON (needed for inference), no server, no lock-in, adding a source = a ~30–60 line config.
- Three-rung ladder: **push raw events (no connector)** → **built-in dlt source** → **bring-your-own `SourcePort`**. Operator-supplied Nango/Airbyte for the exotic tail. Nothing privileged; nobody blocked because we haven't built their tool.
- Honest catch: dlt removes transport, not per-API authoring; ads (Meta/Google) are push-not-pull and deferred.

---

## 11. Interfaces (API/MCP/CLI-first, agent-native)

Every capability is defined **once** (`@capability`: typed input/output + handler + description + examples) and **projected** to FastAPI route + MCP tool + CLI command + JSON Schema. A CI test fails on drift across surfaces. An agent turns *"link this agent to HubSpot and track deals closed"* into our request by filling typed, well-described MCP tool schemas; a `suggest_attribution_rule(nl, source)` helper drafts the structured rule for confirmation rather than guessing. Slack/email are notification sinks reading via capabilities.

---

## 12. Sequencing

1. **Phase 1 — beachhead vendors:** capture (correct COGS) + in-process outcome capture (T1/T2/T3 deterministic join) + **T4 entity-match as the T3-webhook fallback** (H-C: required in Phase 1 because Salesforce-class systems that don't echo metadata fall through to T4) + the eval-backed recommendation *evidence layer*. **No *pull* connectors** (no dlt-based CRM/ticketing pulls) — but **webhook *push* receivers and Slack/email notification sinks ARE in Phase 1** (H11), since outcomes often arrive via the vendor's own webhook. No *semantic* (T5) inference needed. Ship the engine without the hard (pull/identity-resolution) parts.
2. **Phase 2 — broad ICP:** add pull connectors (`dlt` SourcePort) + **cross-system, connector-fed** entity-match and the **T5 semantic-inference** tier for human-in-the-loop outcomes that live in separate systems.
3. **Phase 3 — table stakes:** the cost-visibility dashboard falls out of data we already have; positioned as the floor, never the product. Never compete with LiteLLM/Langfuse on it — integrate them.

---

## 13. Honest limits (carried, never buried)

- Per-request reconciliation is **prorated**, not measured; we label it.
- Client-abort billing is provider-under-documented; we encode the narrow defensible claim and tag `billing_uncertain_abort`.
- Provisioned throughput (Azure PTU/Bedrock) makes token×price meaningless; we refuse to publish a token-derived unit cost there.
- Outcomes are confounded/delayed; they measure the end-to-end system, not the model in isolation — the best label we have, not a perfect one.
- Eval verdicts are valid for the workload distribution at eval time; drift triggers exist because the number rots.
- Semantic inference (T5) and `candidate` bindings are advisory, review-queued, never fed to billing-grade metrics.
- OSS "free per token" is a trap at low volume — surfaced honestly with fully-loaded cost.

---

## 14. Engineering standards (see AGENTS.md / CLAUDE.md)

TDD (red→green→refactor) with the full pyramid (unit + integration against real Postgres/ClickHouse + e2e); strict typing (**pyright --strict + ruff**, pydantic v2 boundaries, no `**kwargs: Any` on public surfaces, `py.typed`); **≥90% coverage on core** (projections/generated excluded); no duplication (one `core`, one capability registry); the three honesty axes are tested invariants.
