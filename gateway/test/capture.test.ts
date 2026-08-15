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
import {
  assignVariant,
  forwardableHeaders,
  readIntent,
  withAssignedVariant,
  withVariantEcho,
} from "../src/headers.js";

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
      foldSseChunk(acc, "data: [DONE]\ndata: {not json}\ndata: \n", ""),
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

describe("experiment assignment", () => {
  it("assigns the same run id to the same arm, every time", async () => {
    // Determinism is the whole contract. A unit of work that lands in arm A on its
    // first call and arm B on its second has been served by both models, so its
    // outcome belongs to neither — and the experiment silently measures a blend
    // rather than a comparison.
    const a = await assignVariant("order_9182", "haiku-vs-opus", [
      "control",
      "haiku",
    ]);
    const b = await assignVariant("order_9182", "haiku-vs-opus", [
      "control",
      "haiku",
    ]);
    expect(a).toBe(b);
  });

  it("splits a population roughly evenly across arms", async () => {
    // A skewed split is not merely inelegant: it lengthens the smaller arm's time
    // to significance, and the sample-size gate is computed per arm.
    const counts: Record<string, number> = { control: 0, haiku: 0 };
    for (let i = 0; i < 2000; i++) {
      const v = await assignVariant(`run-${i}`, "exp", ["control", "haiku"]);
      if (v) counts[v] = (counts[v] ?? 0) + 1;
    }
    expect(counts["control"]).toBeGreaterThan(850);
    expect(counts["haiku"]).toBeGreaterThan(850);
  });

  it("changes assignment when the experiment name changes", async () => {
    // Reusing one hash across experiments correlates their arms: a run in the
    // control of experiment 1 lands in the control of experiment 2 as well, so the
    // second experiment silently inherits the first's selection effects.
    const runs = Array.from({ length: 400 }, (_, i) => `run-${i}`);
    const first = await Promise.all(
      runs.map((r) => assignVariant(r, "exp-1", ["a", "b"])),
    );
    const second = await Promise.all(
      runs.map((r) => assignVariant(r, "exp-2", ["a", "b"])),
    );
    const identical = first.filter((v, i) => v === second[i]).length;
    expect(identical).toBeLessThan(360);
  });

  it("returns undefined when there is nothing to assign", async () => {
    expect(await assignVariant("run-1", "exp", [])).toBeUndefined();
    expect(await assignVariant("run-1", "", ["a", "b"])).toBeUndefined();
  });
});

describe("gateway-side assignment", () => {
  const arms = ["control", "haiku"];

  it("assigns an arm when the host declares an experiment but no variant", async () => {
    // The host says WHICH comparison this call is part of; the gateway decides which
    // side. That is the point: a host choosing its own arms has no randomisation
    // guarantee, and any correlation between its choice and traffic source, time of
    // day or customer size is measured as if it were the model's effect.
    const intent = readIntent(
      new Headers({
        "x-vmx-key": "k",
        "x-vmx-run-id": "order_1",
        "x-vmx-experiment": "e",
      }),
      () => "minted",
    );

    const assigned = await withAssignedVariant(intent, arms);

    expect(arms).toContain(assigned.variant);
  });

  it("never overrides a variant the host set itself", async () => {
    // A host running its own assignment (a feature flag, a staged rollout) is the
    // authority on which arm this call is. Silently relabelling it would make the
    // recorded arm disagree with the model that actually served the request.
    const intent = readIntent(
      new Headers({
        "x-vmx-key": "k",
        "x-vmx-run-id": "order_1",
        "x-vmx-experiment": "e",
        "x-vmx-variant": "host-chose-this",
      }),
      () => "minted",
    );

    const assigned = await withAssignedVariant(intent, arms);

    expect(assigned.variant).toBe("host-chose-this");
  });

  it("leaves ordinary traffic completely untouched", async () => {
    // No experiment means no arm. Stamping one would put every unrelated call into
    // a comparison nobody declared.
    const intent = readIntent(
      new Headers({ "x-vmx-key": "k" }),
      () => "minted",
    );

    const assigned = await withAssignedVariant(intent, arms);

    expect(assigned.variant).toBeUndefined();
    expect(assigned).toEqual(intent);
  });

  it("keeps a unit in one arm across every call it makes", async () => {
    // A unit is many calls. One that draws control on its first call and haiku on
    // its second was served by both models, so its outcome belongs to neither.
    const headers = new Headers({
      "x-vmx-key": "k",
      "x-vmx-run-id": "order_9182",
      "x-vmx-experiment": "e",
    });
    const first = await withAssignedVariant(
      readIntent(headers, () => "m"),
      arms,
    );
    const second = await withAssignedVariant(
      readIntent(headers, () => "m"),
      arms,
    );

    expect(first.variant).toBe(second.variant);
  });
});

describe("declared arms", () => {
  it("reads the arm list the host declared", () => {
    const intent = readIntent(
      new Headers({
        "x-vmx-key": "k",
        "x-vmx-experiment": "e",
        "x-vmx-variants": "control, haiku ,opus",
      }),
      () => "m",
    );

    expect(intent.variants).toEqual(["control", "haiku", "opus"]);
  });

  it("ignores blanks and a list with only separators", () => {
    // A malformed value must degrade to "no experiment to run" rather than create a
    // one-armed comparison or an arm named "".
    const intent = readIntent(
      new Headers({ "x-vmx-key": "k", "x-vmx-variants": " , ,, " }),
      () => "m",
    );

    expect(intent.variants).toEqual([]);
  });

  it("assigns from the declared arms end to end", async () => {
    const intent = readIntent(
      new Headers({
        "x-vmx-key": "k",
        "x-vmx-run-id": "order_1",
        "x-vmx-experiment": "e",
        "x-vmx-variants": "control,haiku",
      }),
      () => "m",
    );

    const assigned = await withAssignedVariant(intent, intent.variants);

    expect(["control", "haiku"]).toContain(assigned.variant);
  });

  it("strips the declaration before forwarding upstream", () => {
    const out = forwardableHeaders(
      new Headers({ "x-vmx-variants": "a,b", authorization: "Bearer sk-1" }),
    );

    expect(out.get("x-vmx-variants")).toBeNull();
    expect(out.get("authorization")).toBe("Bearer sk-1");
  });
});

describe("assignment is observe-only", () => {
  it("echoes the assigned arm back so the host can act on it NEXT call", async () => {
    // The honest limit of an observe-only proxy: by the time the gateway sees a
    // request, the host has already chosen its model. The gateway cannot change that
    // call without rewriting the request, which breaks the founding invariant.
    //
    // So assignment is a two-step contract. The gateway assigns and ECHOES; the host
    // reads the arm and uses it for the calls it makes after. The first call of a new
    // run is served by whatever the host defaulted to and is stamped with that same
    // default only if the host set one — never with an arm nobody served.
    const intent = readIntent(
      new Headers({
        "x-vmx-key": "k",
        "x-vmx-run-id": "order_1",
        "x-vmx-experiment": "e",
        "x-vmx-variants": "control,haiku",
      }),
      () => "m",
    );
    const assigned = await withAssignedVariant(intent, intent.variants);

    const echoed = withVariantEcho(new Response("ok"), assigned);

    expect(echoed.headers.get("x-vmx-variant")).toBe(assigned.variant);
  });

  it("echoes nothing when there was no assignment to make", () => {
    const intent = readIntent(new Headers({ "x-vmx-key": "k" }), () => "m");

    const echoed = withVariantEcho(new Response("ok"), intent);

    expect(echoed.headers.get("x-vmx-variant")).toBeNull();
  });
});
