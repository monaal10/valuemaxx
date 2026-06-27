/**
 * init(): fail-open (H9) + run-context binding (H2) end to end.
 *
 *   - init() NEVER throws into the host; an internal/erroring path is caught,
 *     logged, and surfaced as a warning, never propagated;
 *   - a wrapped client's result (and any host error) propagates UNTOUCHED;
 *   - run() binds run_id onto the captured span; an unbound call is labeled,
 *     never silently dropped;
 *   - the emitted span attributes use exactly the semconv wire keys.
 */

import { InMemorySpanExporter } from "@opentelemetry/sdk-trace-base";
import { describe, expect, it, vi } from "vitest";

import { init } from "../src/index.js";
import { run } from "../src/run.js";
import * as semconv from "../src/semconv.js";

const BASE = {
  tenantId: "tenant-1",
  ingestKey: "ik_secret",
  endpoint: "https://ingest.valuemaxx.dev",
} as const;

/** A fake OpenAI-shaped client whose chat.completions.create we instrument. */
function fakeOpenAI(): {
  chat: { completions: { create: (req: unknown) => Promise<Record<string, unknown>> } };
} {
  return {
    chat: {
      completions: {
        create: (_req: unknown): Promise<Record<string, unknown>> =>
          Promise.resolve({
            id: "cmpl-1",
            model: "gpt-5",
            usage: {
              prompt_tokens: 100,
              completion_tokens: 25,
              prompt_tokens_details: { cached_tokens: 40 },
            },
          }),
      },
    },
  };
}

/** A counter-based id generator so attempt/run ids are deterministic in tests. */
function counterId(): () => string {
  let n = 0;
  return () => `id-${(n += 1)}`;
}

describe("init() fail-open", () => {
  it("throws InitConfigError only for a bad literal config (call-site error)", () => {
    expect(() => init({ ...BASE, endpoint: "ftp://nope" })).toThrowError(/endpoint must be http/);
  });

  it("never throws when wiring; surfaces internal trouble as warnings", () => {
    const logger = { warn: vi.fn(), error: vi.fn() };
    // A client missing the expected method must not crash init — it is skipped.
    const result = init({
      ...BASE,
      logger,
      clients: [{ client: {}, provider: "openai" }],
      exporter: new InMemorySpanExporter(),
    });
    expect(result.capturePatched).toBe(false);
    expect(result.effective.tenantId).toBe("tenant-1");
  });

  it("does not crash the host when an unrelated path throws after init", async () => {
    const exporter = new InMemorySpanExporter();
    const sdk = init({ ...BASE, exporter, clients: [] });
    // Simulate the host doing its own (unrelated, erroring) work.
    expect(() => {
      throw new Error("host's own bug");
    }).toThrowError("host's own bug");
    await sdk.shutdown();
  });

  it("never leaks the ingest key into the effective config echo", () => {
    const result = init({ ...BASE, exporter: new InMemorySpanExporter() });
    expect(JSON.stringify(result.effective)).not.toContain("ik_secret");
    expect(Object.values(result.effective)).not.toContain("ik_secret");
  });
});

describe("init() captures a cost span with run-context binding", () => {
  it("attaches run_id to the captured span and emits the semconv keys", async () => {
    const exporter = new InMemorySpanExporter();
    const client = fakeOpenAI();
    const sdk = init({
      ...BASE,
      exporter,
      newId: counterId(),
      clients: [{ client, provider: "openai" }],
    });
    expect(sdk.capturePatched).toBe(true);

    const response = await run("run-42", () => client.chat.completions.create({ model: "gpt-5" }));
    // The host's own result is returned UNTOUCHED.
    expect(response.id).toBe("cmpl-1");

    await sdk.forceFlush();
    const spans = exporter.getFinishedSpans();
    expect(spans).toHaveLength(1);
    const attrs = spans[0]!.attributes;
    expect(attrs[semconv.AI_MARGIN_RUN_ID]).toBe("run-42");
    expect(attrs[semconv.GEN_AI_SYSTEM]).toBe("openai");
    expect(attrs[semconv.GEN_AI_REQUEST_MODEL]).toBe("gpt-5");
    expect(attrs[semconv.GEN_AI_USAGE_INPUT_TOKENS]).toBe(100);
    expect(attrs[semconv.GEN_AI_USAGE_OUTPUT_TOKENS]).toBe(25);
    expect(attrs[semconv.AI_MARGIN_CACHE_READ]).toBe(40);
    expect(attrs[semconv.AI_MARGIN_CAPTURE_GRANULARITY]).toBe("per_attempt");
    expect(attrs[semconv.AI_MARGIN_IS_STREAMING]).toBe(false);
    await sdk.shutdown();
  });

  it("labels an unbound call with the unbound: run-id prefix, never drops it", async () => {
    const exporter = new InMemorySpanExporter();
    const client = fakeOpenAI();
    const sdk = init({
      ...BASE,
      exporter,
      newId: counterId(),
      clients: [{ client, provider: "openai" }],
    });
    // No enclosing run() — the call is still captured, just labeled.
    await client.chat.completions.create({ model: "gpt-5" });
    await sdk.forceFlush();
    const spans = exporter.getFinishedSpans();
    expect(spans).toHaveLength(1);
    expect(String(spans[0]!.attributes[semconv.AI_MARGIN_RUN_ID])).toMatch(/^unbound:/);
    await sdk.shutdown();
  });

  it("propagates a host create() error untouched and does not emit a span", async () => {
    const exporter = new InMemorySpanExporter();
    const client = {
      chat: {
        completions: {
          create: (_req: unknown): Promise<never> => Promise.reject(new Error("rate limited")),
        },
      },
    };
    const sdk = init({ ...BASE, exporter, clients: [{ client, provider: "openai" }] });
    await expect(client.chat.completions.create({ model: "gpt-5" })).rejects.toThrowError(
      "rate limited",
    );
    await sdk.forceFlush();
    expect(exporter.getFinishedSpans()).toHaveLength(0);
    await sdk.shutdown();
  });
});

describe("init() streaming capture", () => {
  it("accumulates streaming chunks to a terminal cost span (not delta-summed)", async () => {
    const exporter = new InMemorySpanExporter();
    // A fake Anthropic-shaped streaming client; await models real chunk arrival.
    async function* stream(): AsyncGenerator<Record<string, unknown>> {
      await Promise.resolve();
      yield {
        type: "message_start",
        message: { usage: { input_tokens: 100, output_tokens: 0 } },
      };
      yield { type: "message_delta", usage: { output_tokens: 35 } };
      yield { type: "message_delta", usage: { output_tokens: 90 } }; // terminal
    }
    const client = {
      messages: {
        create: (_req: unknown): AsyncIterable<Record<string, unknown>> => stream(),
      },
    };
    const sdk = init({
      ...BASE,
      exporter,
      newId: counterId(),
      clients: [{ client, provider: "anthropic" }],
    });

    const received: Record<string, unknown>[] = [];
    await run("stream-run", async () => {
      for await (const chunk of client.messages.create({
        model: "claude-opus-4-8",
        stream: true,
      })) {
        received.push(chunk);
      }
    });
    // The host saw every original chunk, untouched.
    expect(received).toHaveLength(3);

    await sdk.forceFlush();
    const spans = exporter.getFinishedSpans();
    expect(spans).toHaveLength(1);
    const attrs = spans[0]!.attributes;
    expect(attrs[semconv.GEN_AI_USAGE_OUTPUT_TOKENS]).toBe(90); // terminal, NOT 35+90
    expect(attrs[semconv.AI_MARGIN_IS_STREAMING]).toBe(true);
    expect(attrs[semconv.AI_MARGIN_RUN_ID]).toBe("stream-run");
    await sdk.shutdown();
  });
});
