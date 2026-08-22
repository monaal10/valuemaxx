import { describe, expect, it } from "vitest";

import {
  applyBoundedPatch,
  configIdentity,
  isInRollout,
  parseDeploymentPolicy,
  prepareRequestBody,
} from "../src/config.js";

describe("config identity", () => {
  it("is stable across JSON object key order while preserving array order", async () => {
    const first = JSON.stringify({
      model: "gpt-5",
      messages: [
        { role: "system", content: "Be concise" },
        { role: "user", content: "hello" },
      ],
      tools: [{ type: "function", function: { name: "lookup", strict: true } }],
      max_tokens: 200,
    });
    const second = JSON.stringify({
      max_tokens: 200,
      tools: [{ function: { strict: true, name: "lookup" }, type: "function" }],
      messages: [
        { content: "Be concise", role: "system" },
        { content: "different conversation", role: "user" },
      ],
      model: "gpt-5",
    });

    expect(await configIdentity("openai", first)).toEqual(
      await configIdentity("openai", second),
    );
  });

  it("keeps system, tools, and params as separately attributable hashes", async () => {
    const base = JSON.stringify({
      model: "claude-sonnet-4",
      system: "You are helpful",
      tools: [{ name: "lookup", input_schema: { type: "object" } }],
      max_tokens: 100,
    });
    const changed = JSON.stringify({
      model: "claude-haiku-4",
      system: "You are helpful",
      tools: [{ name: "lookup", input_schema: { type: "object" } }],
      max_tokens: 100,
    });

    const a = await configIdentity("anthropic", base);
    const b = await configIdentity("anthropic", changed);
    expect(a?.systemHash).toBe(b?.systemHash);
    expect(a?.toolsHash).toBe(b?.toolsHash);
    expect(a?.paramsHash).not.toBe(b?.paramsHash);
    expect(a?.configId).not.toBe(b?.configId);
  });

  it("attributes an embedded cache breakpoint to params, not prompt semantics", async () => {
    const first = JSON.stringify({
      model: "claude-sonnet-4",
      system: [{ type: "text", text: "Stable", cache_control: { type: "ephemeral" } }],
      tools: [{ name: "lookup", cache_control: { type: "ephemeral", ttl: "5m" } }],
      max_tokens: 100,
    });
    const second = JSON.stringify({
      model: "claude-sonnet-4",
      system: [{ type: "text", text: "Stable", cache_control: { type: "ephemeral", ttl: "1h" } }],
      tools: [{ name: "lookup" }],
      max_tokens: 100,
    });
    const a = await configIdentity("anthropic", first);
    const b = await configIdentity("anthropic", second);

    expect(a?.systemHash).toBe(b?.systemHash);
    expect(a?.toolsHash).toBe(b?.toolsHash);
    expect(a?.paramsHash).not.toBe(b?.paramsHash);
  });

  it("returns undefined for a non-object or malformed body", async () => {
    expect(await configIdentity("openai", "not-json")).toBeUndefined();
    expect(await configIdentity("openai", "[]")).toBeUndefined();
  });
});

describe("bounded provider mutation", () => {
  it("changes only OpenAI model, reasoning effort, and token cap", () => {
    const original = JSON.stringify({
      model: "gpt-5",
      messages: [{ role: "user", content: "hello" }],
      tools: [{ type: "function", function: { name: "lookup" } }],
      temperature: 0.2,
      max_completion_tokens: 500,
    });
    const mutated = applyBoundedPatch("openai", original, {
      model: "gpt-5-mini",
      reasoningEffort: "low",
      maxTokens: 120,
    });
    const parsed = JSON.parse(mutated ?? "null") as Record<string, unknown>;

    expect(parsed).toMatchObject({
      model: "gpt-5-mini",
      reasoning_effort: "low",
      max_completion_tokens: 120,
      temperature: 0.2,
    });
    expect(parsed.messages).toEqual([{ role: "user", content: "hello" }]);
    expect(parsed.tools).toEqual([{ type: "function", function: { name: "lookup" } }]);
  });

  it("uses Anthropic and Gemini native parameter shapes", () => {
    const anthropic = applyBoundedPatch(
      "anthropic",
      JSON.stringify({ model: "claude-a", max_tokens: 500, messages: [] }),
      { model: "claude-b", reasoningEffort: "low", maxTokens: 100 },
    );
    expect(JSON.parse(anthropic ?? "null")).toMatchObject({
      model: "claude-b",
      max_tokens: 100,
      output_config: { effort: "low" },
    });

    const gemini = applyBoundedPatch(
      "gemini",
      JSON.stringify({ contents: [], generationConfig: { temperature: 0.3 } }),
      { reasoningEffort: "low", maxTokens: 80 },
    );
    expect(JSON.parse(gemini ?? "null")).toMatchObject({
      generationConfig: {
        temperature: 0.3,
        maxOutputTokens: 80,
        thinkingConfig: { thinkingLevel: "low" },
      },
    });
  });

  it("fails open for malformed input or an invalid patch", () => {
    expect(applyBoundedPatch("openai", "not-json", { model: "x" })).toBeUndefined();
    expect(
      applyBoundedPatch("openai", JSON.stringify({ model: "x" }), { maxTokens: 0 }),
    ).toBeUndefined();
    expect(
      applyBoundedPatch("gemini", JSON.stringify({ contents: [] }), { model: "gemini-x" }),
    ).toBeUndefined();
  });
});

describe("rollout and policy", () => {
  it("makes deterministic and monotonic 1/5/25/100 assignments", async () => {
    for (let i = 0; i < 300; i++) {
      const run = `run-${i}`;
      const at1 = await isInRollout("dep-1", run, 1);
      const at5 = await isInRollout("dep-1", run, 5);
      const at25 = await isInRollout("dep-1", run, 25);
      const at100 = await isInRollout("dep-1", run, 100);
      expect(at1 && !at5).toBe(false);
      expect(at5 && !at25).toBe(false);
      expect(at100).toBe(true);
      expect(await isInRollout("dep-1", run, 25)).toBe(at25);
    }
  });

  it("accepts only bounded, source-matched deployment policies", () => {
    expect(
      parseDeploymentPolicy(
        JSON.stringify({
          id: "dep-1",
          provider: "openai",
          callSiteId: "checkout.classify",
          sourceConfigId: "source",
          rolloutPercent: 5,
          patch: { model: "gpt-5-mini", maxTokens: 100 },
        }),
      ),
    ).toEqual({
      id: "dep-1",
      provider: "openai",
      callSiteId: "checkout.classify",
      sourceConfigId: "source",
      rolloutPercent: 5,
      patch: { model: "gpt-5-mini", maxTokens: 100 },
    });
    expect(
      parseDeploymentPolicy(
        JSON.stringify({
          id: "dep-1",
          provider: "openai",
          callSiteId: "checkout.classify",
          sourceConfigId: "source",
          rolloutPercent: 10,
          patch: { temperature: 1 },
        }),
      ),
    ).toBeUndefined();
  });

  it("is observe-only unless enabled, source-matched, enrolled, and not bypassed", async () => {
    const original = JSON.stringify({ model: "gpt-5", messages: [] });
    const source = await configIdentity("openai", original);
    const policyRaw = JSON.stringify({
      id: "dep-1",
      provider: "openai",
      callSiteId: "checkout.classify",
      sourceConfigId: source?.configId,
      rolloutPercent: 100,
      patch: { model: "gpt-5-mini" },
    });
    const base = {
      provider: "openai" as const,
      originalBody: original,
      runId: "run-1",
      callSiteId: "checkout.classify",
      policyRaw,
    };

    expect((await prepareRequestBody({ ...base, bypass: false, enforcementEnabled: false })).body)
      .toBe(original);
    expect((await prepareRequestBody({ ...base, bypass: true, enforcementEnabled: true })).body)
      .toBe(original);
    expect(
      (await prepareRequestBody({
        ...base,
        callSiteId: "other",
        bypass: false,
        enforcementEnabled: true,
      })).body,
    ).toBe(original);
    const applied = await prepareRequestBody({
      ...base,
      bypass: false,
      enforcementEnabled: true,
    });
    expect(JSON.parse(applied.body ?? "null")).toMatchObject({ model: "gpt-5-mini" });
    expect(applied.deploymentId).toBe("dep-1");
    expect(applied.identity?.configId).not.toBe(source?.configId);
  });
});
