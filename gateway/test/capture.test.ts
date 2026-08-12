/**
 * Capture correctness — the part a proxy cannot get away with approximating.
 *
 * These pin the two failure modes that make a cost number silently wrong rather than
 * absent: double-counting cached input, and losing a stream that ended early. Both
 * were real bugs in the SDK's history; the accumulators encode the fixes, and these
 * tests prove the gateway drives them correctly from raw bytes.
 */

import { describe, expect, it } from "vitest";

import {
  foldSseChunk,
  newAccumulator,
  observeNonStreaming,
  readInlineCost,
} from "../src/capture.js";
import { forwardableHeaders, readIntent } from "../src/headers.js";

describe("SSE folding", () => {
  it("counts an anthropic stream's tokens without double-counting cache", () => {
    const acc = newAccumulator("anthropic");
    const frames = [
      'data: {"type":"message_start","message":{"usage":{"input_tokens":100,"cache_read_input_tokens":900}}}',
      'data: {"type":"message_delta","usage":{"output_tokens":10}}',
      // Anthropic re-sends the running total; it must OVERWRITE, not accumulate.
      'data: {"type":"message_delta","usage":{"output_tokens":42}}',
      "",
    ].join("\n");

    const carry = foldSseChunk(acc, frames, "");

    expect(carry).toBe("");
    const obs = acc.finalizeObservation({
      provider: "anthropic",
      model: "claude-x",
    });
    expect(obs.tokens.inputUncached).toBe(100);
    expect(obs.tokens.cacheRead).toBe(900);
    expect(obs.tokens.output).toBe(42); // not 52
  });

  it("threads a frame split across two chunks", () => {
    // A chunk boundary mid-JSON is normal on the wire. Dropping the frame would
    // silently under-report; concatenating wrongly would throw.
    const acc = newAccumulator("anthropic");
    const whole =
      'data: {"type":"message_start","message":{"usage":{"input_tokens":7,"cache_read_input_tokens":0}}}\n';
    const split = Math.floor(whole.length / 2);

    let carry = foldSseChunk(acc, whole.slice(0, split), "");
    carry = foldSseChunk(acc, whole.slice(split), carry);

    expect(
      acc.finalizeObservation({ provider: "anthropic", model: "m" }).tokens
        .inputUncached,
    ).toBe(7);
  });

  it("skips [DONE] and malformed frames instead of throwing", () => {
    const acc = newAccumulator("openai");
    expect(() =>
      foldSseChunk(acc, 'data: [DONE]\ndata: {not json}\ndata: \n', ""),
    ).not.toThrow();
  });

  it("a cancelled stream still reports what it saw, flagged partial", () => {
    // A client disconnecting mid-stream is the case where naive proxies report zero.
    const acc = newAccumulator("anthropic");
    foldSseChunk(
      acc,
      'data: {"type":"message_start","message":{"usage":{"input_tokens":50,"cache_read_input_tokens":0}}}\n',
      "",
    );
    acc.markCancelled();

    const obs = acc.finalizeObservation({ provider: "anthropic", model: "m" });
    expect(obs.tokens.inputUncached).toBe(50);
    expect(obs.partialRecovered).toBe(true);
  });
});

describe("non-streaming usage", () => {
  it("treats openai cached tokens as a SUBSET of prompt_tokens", () => {
    // `prompt_tokens` INCLUDES cached. Adding them would bill the input twice.
    const obs = observeNonStreaming(
      "openai",
      {
        model: "gpt-x",
        usage: {
          prompt_tokens: 1000,
          completion_tokens: 20,
          prompt_tokens_details: { cached_tokens: 800 },
        },
      },
      "",
    );
    expect(obs?.tokens.inputUncached).toBe(200);
    expect(obs?.tokens.cacheRead).toBe(800);
  });

  it("treats gemini cachedContent as a subset of promptTokenCount", () => {
    const obs = observeNonStreaming(
      "gemini",
      {
        usageMetadata: {
          promptTokenCount: 500,
          cachedContentTokenCount: 100,
          candidatesTokenCount: 30,
          thoughtsTokenCount: 5,
        },
      },
      "gemini-x",
    );
    expect(obs?.tokens.inputUncached).toBe(400);
    expect(obs?.tokens.cacheRead).toBe(100);
    expect(obs?.tokens.reasoning).toBe(5);
  });

  it("falls back to the REQUESTED model when the body omits it", () => {
    const obs = observeNonStreaming(
      "anthropic",
      { usage: { input_tokens: 1, output_tokens: 1 } },
      "claude-from-request",
    );
    expect(obs?.model).toBe("claude-from-request");
  });

  it("returns nothing when there is no usage block to read", () => {
    expect(observeNonStreaming("openai", { model: "x" }, "")).toBeUndefined();
  });
});

describe("openrouter inline cost", () => {
  it("reads an authoritative billed cost", () => {
    expect(readInlineCost({ usage: { cost: 0.0042 } })).toBe(0.0042);
  });

  it("refuses a cost the provider flagged as an estimate", () => {
    // Laundering a labeled guess into the reconciled tier is the exact dishonesty
    // the provenance axis exists to prevent.
    expect(
      readInlineCost({ usage: { cost: 0.0042, is_estimate: true } }),
    ).toBeUndefined();
  });
});

describe("header contract", () => {
  it("reads the full intent from headers", () => {
    const intent = readIntent(
      new Headers({
        "x-vmx-key": "vmx_live_1",
        "x-vmx-run-id": "order_9182",
        "x-vmx-agent": "support-bot",
        "x-vmx-entity-customer-id": "c_1",
        "x-vmx-outcome": "ticket_resolved",
      }),
      () => "minted",
    );

    expect(intent.key).toBe("vmx_live_1");
    expect(intent.runId).toBe("order_9182");
    expect(intent.runIdWasMinted).toBe(false);
    expect(intent.agentName).toBe("support-bot");
    // Hyphens become underscores so the header reads naturally but the entity key
    // matches the snake_case the backend stores.
    expect(intent.entityKeys).toEqual({ customer_id: "c_1" });
    expect(intent.outcome).toBe("ticket_resolved");
  });

  it("mints a run id when none is supplied, and says so", () => {
    const intent = readIntent(new Headers(), () => "minted-1");
    expect(intent.runId).toBe("minted-1");
    expect(intent.runIdWasMinted).toBe(true);
  });

  it("accepts a W3C baggage run id as an alias", () => {
    const intent = readIntent(
      new Headers({ baggage: "valuemaxx.run_id=run-b,other=x" }),
      () => "minted",
    );
    expect(intent.runId).toBe("run-b");
    expect(intent.runIdWasMinted).toBe(false);
  });

  it("prefers the explicit header over baggage", () => {
    const intent = readIntent(
      new Headers({
        "x-vmx-run-id": "explicit",
        baggage: "valuemaxx.run_id=from-baggage",
      }),
      () => "minted",
    );
    expect(intent.runId).toBe("explicit");
  });

  it("strips every x-vmx header before forwarding upstream", () => {
    // The provider must see exactly the request the host wrote. Leaking our headers
    // is at best noise and at worst a rejected request.
    const out = forwardableHeaders(
      new Headers({
        authorization: "Bearer sk-real",
        "content-type": "application/json",
        "x-vmx-key": "vmx_live_1",
        "x-vmx-outcome": "done",
        host: "gw.valuemaxx.dev",
      }),
    );

    expect(out.get("authorization")).toBe("Bearer sk-real");
    expect(out.get("content-type")).toBe("application/json");
    expect(out.get("x-vmx-key")).toBeNull();
    expect(out.get("x-vmx-outcome")).toBeNull();
    expect(out.get("host")).toBeNull();
  });
});

describe("experiment fields", () => {
  it("reads experiment, variant and app from headers", () => {
    // These carry no engine yet. They are read now because they cannot be
    // retrofitted: traffic that ran without a variant stamp can never be told
    // apart afterwards, so any comparison over history depends on stamping it
    // before the history is made.
    const intent = readIntent(
      new Headers({
        "x-vmx-key": "k",
        "x-vmx-experiment": "haiku-vs-opus",
        "x-vmx-variant": "haiku",
        "x-vmx-app": "support",
      }),
      () => "minted",
    );

    expect(intent.experiment).toBe("haiku-vs-opus");
    expect(intent.variant).toBe("haiku");
    expect(intent.app).toBe("support");
  });

  it("leaves them undefined when unsent, and strips them upstream", () => {
    const intent = readIntent(new Headers({ "x-vmx-key": "k" }), () => "m");
    expect(intent.experiment).toBeUndefined();
    expect(intent.variant).toBeUndefined();
    expect(intent.app).toBeUndefined();

    const out = forwardableHeaders(
      new Headers({ "x-vmx-experiment": "e", authorization: "Bearer sk-1" }),
    );
    expect(out.get("x-vmx-experiment")).toBeNull();
    expect(out.get("authorization")).toBe("Bearer sk-1");
  });
});
