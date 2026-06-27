# valuemaxx

**AI Margin Intelligence for Node.** One line of setup gives you correct,
per-attempt LLM cost telemetry for the OpenAI and Anthropic Node clients and the
Vercel AI SDK — emitted over OTLP, on the exact same wire contract as the
[Python SDK](https://pypi.org/project/valuemaxx/).

It is **real OpenTelemetry instrumentation, not a shim**: the OpenAI/Anthropic
Node SDKs don't natively emit OTel spans, so `valuemaxx` installs a purpose-built,
instance-scoped wrapper plus an OTLP/HTTP exporter. Streaming cost is accumulated
to **terminal** token values across chunks before the cost span is emitted (no
delta-summing, no cache double-counting).

- **Fails open, always.** Internal errors are caught, logged, and counted —
  `init()` and the wrappers **never** throw into your call path.
- **Content off by default.** Cost capture needs only token counts + metadata;
  prompt/response content is never captured unless you opt in.
- **Secret-safe.** The ingest key is held in a `SecretString` that never appears
  in a log, a thrown error, or a serialized config.
- **Self-testing.** On startup it checks installed SDK versions + that the hook
  took effect, and **warns loudly** (degrading to `per_call`) if it can't capture
  per-attempt — never silently captures nothing.

## Install

```sh
npm install valuemaxx
# or: pnpm add valuemaxx / yarn add valuemaxx
```

Node ≥ 20.

## Quick start

```ts
import { init } from "valuemaxx";

const vmx = init({
  tenantId: process.env.VALUEMAXX_TENANT_ID!,
  ingestKey: process.env.VALUEMAXX_INGEST_KEY!,
  endpoint: process.env.VALUEMAXX_ENDPOINT ?? "https://ingest.valuemaxx.dev/v1/traces",
});
```

That's it for the universal OTLP path. To capture cost off your provider clients,
hand `init()` the client instances:

```ts
import OpenAI from "openai";
import Anthropic from "@anthropic-ai/sdk";
import { init, run } from "valuemaxx";

const openai = new OpenAI();
const anthropic = new Anthropic();

init({
  tenantId: process.env.VALUEMAXX_TENANT_ID!,
  ingestKey: process.env.VALUEMAXX_INGEST_KEY!,
  endpoint: process.env.VALUEMAXX_ENDPOINT!,
  clients: [
    { client: openai, provider: "openai" },
    { client: anthropic, provider: "anthropic" },
  ],
});

// Every LLM call inside `run` binds to this run id (rides AsyncLocalStorage).
await run("checkout-agent-42", async () => {
  await openai.chat.completions.create({ model: "gpt-4.1", messages: [...] });
  // streaming is accumulated to terminal usage automatically:
  for await (const _ of anthropic.messages.create({ model: "claude-...", stream: true, messages: [...] })) {
    // your normal handling — chunks pass through untouched
  }
});
```

A call made outside any `run(...)` is still captured — just labeled with an
`unbound:` run id, never silently dropped.

### Vercel AI SDK

The AI SDK already emits OTel spans; pass it the tracer `init()` returns:

```ts
import { streamText } from "ai";
import { init } from "valuemaxx";

const { tracer } = init({ tenantId, ingestKey, endpoint });

await streamText({
  model: openai("gpt-4.1"),
  prompt: "...",
  experimental_telemetry: { isEnabled: true, tracer },
});
```

## Config

| Option           | Type                     | Default       | Notes                                                        |
| ---------------- | ------------------------ | ------------- | ------------------------------------------------------------ |
| `tenantId`       | `string` (required)      | —             | Tenant scope; rides every span as `ai_margin.tenant_id`.     |
| `ingestKey`      | `string` (required)      | —             | Per-tenant ingest key; sent as an auth header. Never logged. |
| `endpoint`       | `string` (required)      | —             | OTLP/HTTP traces endpoint. Must be `http(s)`.                |
| `captureContent` | `boolean`                | `false`       | Capture prompt/response content. Off by default.             |
| `serviceName`    | `string`                 | `"valuemaxx"` | OTel `service.name` resource attribute.                      |
| `clients`        | `{ client, provider }[]` | `[]`          | OpenAI/Anthropic instances to instrument.                    |

`init()` returns an `InitResult` with the effective config echo (no secret),
`captureGranularity`, any `warnings`, the `tracer`, reversible `handles`, plus
`forceFlush()` and `shutdown()`.

## Why per-attempt + terminal usage matters

Naively summing streaming `message_delta` usage double-counts cache tokens (the
known `@langchain/anthropic` 2× bug) and inflates output. `valuemaxx` takes the
**terminal** cumulative value for output and reads cache tokens from
`message_start` exactly once, splitting 5-minute vs 1-hour cache writes — the same
correctness rules the Python SDK enforces. A cancelled stream recovers whatever
terminal value it has and flags `ai_margin.partial_recovered`, never a silent zero.

## License

Apache-2.0
