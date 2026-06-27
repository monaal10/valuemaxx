# valuemaxx

**stop tokenmaxxing. start valuemaxxing.** — *the anti-tokenmaxxing tool*

> **Know what each AI agent actually costs you — correctly — and what it earned, per outcome, with confidence.**
> For teams that **build** AI agents, not the ones who buy them.

Observability tools (Helicone, Langfuse) tell you what you **spent**. This tells you whether it was **worth it**: it captures *correct, invoice-reconciled* LLM cost per agent run, deterministically binds it to the real business outcome each run produced — including outcomes that arrive days later, out of process — and labels every number with how trustworthy it is. Then it shows you, on your real workload, where a cheaper or faster model holds the same outcome.

> **Status:** pre-1.0, under active development. The design and build plan live in [`docs/plans/`](./docs/plans/).

---

## Why this exists

If you build an AI product (a support agent, an SDR agent, an AI feature), your tokens *are* your cost of goods. Most homegrown cost numbers are wrong by 8–15% (streaming-disconnect undercounts, invisible retries, mis-priced cache tokens). And almost nobody can answer "did this agent run actually make money?" — because the cost lives in your logs and the outcome lives in your product or your CRM.

This tool closes both gaps, and it's honest about precision the whole way: every figure carries a **provenance** (was it measured, estimated, or reconciled to the invoice?), every cost↔outcome link carries a **binding tier** (exact key, deterministic round-trip, fuzzy match), and every outcome carries a **signal class** (did the action just *happen*, or is the business result *confirmed*?).

## How it works (the short version)

1. **`init()` — one line.** A thin SDK (Python *and* TypeScript) captures every LLM call's *correct* cost, off the hot path, and never throws into your app.
2. **Declare your outcomes once.** A config (`outcomes.yaml`) — which the onboarding agent writes for you by reading your codebase — says what a "resolution" / "deal" / "funded loan" *is* in your system. No per-call tracking code.
3. **Cost binds to outcome automatically.** In-process outcomes bind via execution context; delayed/external outcomes bind via a round-tripped correlation id (we stamp it on your outbound call; the webhook echoes it back). Everything is confidence-labeled.
4. **See your margin, and where to cut it.** Cost-per-outcome and gross-margin rollups; and an eval layer that replays cheaper models against your real workload and recommends switches — with the evidence, never automatically.

## Install

```bash
# Python
pip install valuemaxx

# TypeScript / JavaScript
npm install valuemaxx
```

```python
import valuemaxx
valuemaxx.init()                      # zero-code cost capture starts here
```

```ts
import { init } from "valuemaxx";
init();
```

> Both SDKs are thin producers over a shared OpenTelemetry wire contract; the backend is self-hostable and language-agnostic.

## Integrate with an AI coding agent (Claude Code / Cursor)

This project is built to be wired up **by** a coding agent. Point your agent at the shipped onboarding skill and it will:
- scan your codebase, find where your agent runs and where outcomes are recorded,
- propose the `outcomes.yaml` (and the run-id injection for delayed outcomes),
- show you a reviewable diff — you just approve it.

See [`docs/onboarding/`](./docs/onboarding/) for the onboarding prompts and the skill.

## The honesty model

Three system axes ride every number and never get laundered upward (a rollup always shows the *least-trusted* of its parts):

| Axis | Values |
|---|---|
| **Cost provenance** | `measured` · `estimated` · `allocated` · `provider_reconciled` · `manual_reconciled` |
| **Binding tier** | `exact` · `deterministic` · `candidate` · `likely` |
| **Outcome signal class** | `action_attempted` · `outcome_confirmed` · `outcome_retracted` |

## Self-hosting & data

Designed to run on a container + Postgres (SQLite for local dev). Prompt/response **content is off by default**; it's only retained (self-host only) if you enable it for the eval/replay features, with a configurable TTL and an erasure path. Provider API keys for eval are **never persisted**.

## Contributing

Engineering standards are strict and binding — see [`AGENTS.md`](./AGENTS.md): test-driven development (unit + integration + e2e), `pyright --strict` + `ruff`, ≥90% coverage on core, and a **ratchet** discipline (every bug becomes a permanent conformance rule so its class can't recur).

## License

Apache-2.0 — see [`LICENSE`](./LICENSE).
