# valuemaxx (Python SDK)

> **Know what each AI agent actually costs you — correctly — and what it earned, per outcome, with confidence.**

The Python SDK for [valuemaxx](https://github.com/monaal10/valuemaxx) — *AI margin intelligence for teams that build AI agents*. One line captures the **correct** cost of every LLM call (off the hot path, never throwing into your app), so valuemaxx can bind it to the business outcome each agent run produced.

## Install

```bash
pip install valuemaxx
```

## Use

```python
import valuemaxx

valuemaxx.init()   # zero-code cost capture starts here
```

That's it. `init()` instruments the `openai` / `anthropic` clients (and frameworks that use them — LangChain, LlamaIndex, CrewAI) at the transport layer, capturing correct token/cost per call: streaming usage taken from terminal values (never delta-summed), cache token classes priced separately, retries counted. It **fails open** — internal errors are caught and logged, never propagated into your call path, and it adds <1ms.

### Attribute a run to an outcome

Wrap a unit of work so its cost can later be tied to a business outcome:

```python
with valuemaxx.run(customer_id=user.id):
    response = client.messages.create(...)   # cost captured AND tagged to this run
```

The entity IDs you pass are the natural keys valuemaxx uses to bind delayed/out-of-process outcomes (a deal closing days later, a ticket resolving) back to the run that caused them — with an honest confidence label on every link.

## What's captured (and what isn't)

- **Captured:** model, token counts (input / cache-read / cache-write / output / reasoning), computed cost with provenance (`measured` → reconciled to the provider invoice later), latency, the run context.
- **Off by default:** prompt/response **content** (PII-sensitive). Enable it only for the eval/replay features, on self-hosted deployments.

## The honesty model

Every number valuemaxx produces carries its trustworthiness — cost provenance (`measured`/`estimated`/`allocated`/`provider_reconciled`), and once joined to outcomes, a binding tier and signal class. A rollup always shows the *least-trusted* of its parts; estimates never render as billed.

## Self-hosting

The SDK ships telemetry over OTLP/HTTP to a valuemaxx backend you run (a container + Postgres; SQLite for local dev). The SDK itself holds nothing and needs no database. See the [main repo](https://github.com/monaal10/valuemaxx) for the backend, the TypeScript SDK (`npm i valuemaxx`), and the onboarding flow that wires outcomes for you.

## License

Apache-2.0
