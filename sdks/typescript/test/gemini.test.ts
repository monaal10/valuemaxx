/**
 * Gemini (Google) direct-client instrumentation.
 *
 * Direct-client capture supported only OpenAI + Anthropic; a real codebase using the
 * Google GenAI SDK (`@google/genai`, `client.models.generateContent`) got no capture.
 * This adds a `google` provider: the non-streaming extractor reads Gemini's
 * `usageMetadata` and maps it onto the canonical token vector.
 *
 * Gemini token semantics (from the GenerateContentResponse.usageMetadata contract):
 *   - `promptTokenCount` is the TOTAL input, INCLUSIVE of cached content;
 *   - `cachedContentTokenCount` is the cached subset of the prompt (cache read);
 *   - `candidatesTokenCount` is the visible output;
 *   - `thoughtsTokenCount` is reasoning (thinking), counted SEPARATELY by Gemini but
 *     billed as output — so total output = candidates + thoughts, reasoning embedded.
 * So `inputUncached = promptTokenCount - cachedContentTokenCount`, cache_read =
 * cachedContentTokenCount, output = candidatesTokenCount + thoughtsTokenCount,
 * reasoning = thoughtsTokenCount — the same total-plus-subset shape as the others.
 */

import { InMemorySpanExporter } from "@opentelemetry/sdk-trace-base";
import { describe, expect, it } from "vitest";

import { init } from "../src/index.js";
import { extractNonStreaming } from "../src/instrumentation.js";
import { run } from "../src/run.js";
import * as semconv from "../src/semconv.js";

const BASE = {
  tenantId: "tenant-1",
  ingestKey: "ik_secret",
  endpoint: "https://ingest.valuemaxx.dev",
} as const;

/** A fake @google/genai-shaped client: `client.models.generateContent(...)`. */
function fakeGemini(): {
  models: { generateContent: (req: unknown) => Promise<Record<string, unknown>> };
} {
  return {
    models: {
      generateContent: (_req: unknown): Promise<Record<string, unknown>> =>
        Promise.resolve({
          modelVersion: "gemini-2.5-flash",
          usageMetadata: {
            promptTokenCount: 1000,
            cachedContentTokenCount: 200,
            candidatesTokenCount: 250,
            thoughtsTokenCount: 50,
          },
        }),
    },
  };
}

describe("Gemini non-streaming usage extraction", () => {
  it("maps usageMetadata onto the canonical token vector", () => {
    const response = {
      modelVersion: "gemini-2.5-flash",
      usageMetadata: {
        promptTokenCount: 1000, // total input (incl. cached)
        cachedContentTokenCount: 200,
        candidatesTokenCount: 250,
        thoughtsTokenCount: 50,
        totalTokenCount: 1250,
      },
    };

    const obs = extractNonStreaming(response, "gemini-2.5-flash", "google");
    expect(obs).not.toBeNull();
    expect(obs?.provider).toBe("google");
    expect(obs?.model).toBe("gemini-2.5-flash");
    // 1000 total input = 200 cache_read + 800 uncached
    expect(obs?.tokens.inputUncached).toBe(800);
    expect(obs?.tokens.cacheRead).toBe(200);
    // output = candidates(250) + thoughts(50) = 300, with reasoning embedded
    expect(obs?.tokens.output).toBe(300);
    expect(obs?.tokens.reasoning).toBe(50);
  });

  it("handles a response with no cached tokens", () => {
    const response = {
      usageMetadata: { promptTokenCount: 500, candidatesTokenCount: 120 },
    };
    const obs = extractNonStreaming(response, "gemini-2.0-flash", "google");
    expect(obs?.tokens.inputUncached).toBe(500);
    expect(obs?.tokens.cacheRead).toBe(0);
    expect(obs?.tokens.output).toBe(120);
    expect(obs?.tokens.reasoning).toBe(0);
  });

  it("returns null when usageMetadata is absent (fail-soft, no fabricated tokens)", () => {
    expect(
      extractNonStreaming({ modelVersion: "gemini-2.5-flash" }, "gemini-2.5-flash", "google"),
    ).toBeNull();
  });
});

describe("init() instruments a Gemini client end to end", () => {
  it("captures a generateContent call as a span with gen_ai.system=google", async () => {
    const exporter = new InMemorySpanExporter();
    const client = fakeGemini();
    const result = init({
      ...BASE,
      clients: [{ client, provider: "google" }],
      exporter,
      newId: (() => {
        let n = 0;
        return () => `id-${(n += 1)}`;
      })(),
    });
    expect(result.capturePatched).toBe(true);

    await run("gemini-run", async () => {
      await client.models.generateContent({ model: "gemini-2.5-flash" });
    });
    await result.forceFlush();

    const spans = exporter.getFinishedSpans();
    expect(spans.length).toBe(1);
    const attrs = spans[0]?.attributes ?? {};
    expect(attrs[semconv.GEN_AI_SYSTEM]).toBe("google");
    expect(attrs[semconv.GEN_AI_REQUEST_MODEL]).toBe("gemini-2.5-flash");
    // total input 1000 (800 uncached + 200 cache_read); output 250 + 50 thoughts = 300.
    expect(attrs[semconv.GEN_AI_USAGE_INPUT_TOKENS]).toBe(1000);
    expect(attrs[semconv.GEN_AI_USAGE_OUTPUT_TOKENS]).toBe(300);
    await result.shutdown();
  });
});
