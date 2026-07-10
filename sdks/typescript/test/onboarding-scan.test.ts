/**
 * TS onboarding scanner unit tests — mirror packages/onboarding/tests/test_ts_scan.py so the
 * TS scanner detects the same run boundaries, outcome sites, entity ids, and redacts secrets
 * exactly like the Python one. (The golden parity test asserts full-pipeline equivalence;
 * these pin the scanner's behavior directly.)
 */

import { describe, expect, it } from "vitest";

import rulesJson from "../src/onboarding/onboarding_rules.json" with { type: "json" };
import { scanTsSource } from "../src/onboarding/scan.js";
import type { OnboardingRules } from "../src/onboarding/types.js";

const rules = rulesJson as OnboardingRules;

const VERCEL_AI_SRC = `
import { generateText, streamText } from "ai";
import { createOpenAI } from "@ai-sdk/openai";

export async function answer(conversationId: string, customerId: string) {
  const openai = createOpenAI({ apiKey: process.env.OPENAI_API_KEY });
  const result = await generateText({ model: openai("gpt-5"), prompt: "hi" });
  return result;
}

export async function stream(applicationId: string) {
  return streamText({ model: openai("gpt-5"), prompt: "go" });
}

export async function markResolved(ticket: Ticket) {
  ticket.status = "resolved";
  await ticket.save();
}
`;

const WITH_SECRET = `
const KEY = "sk-ant-api03-REALSECRETVALUE1234567890abcdefghij";
export async function go() {
  return generateText({ apiKey: KEY, prompt: "x" });
}
`;

describe("TS onboarding scanner", () => {
  it("finds Vercel AI SDK run boundaries (generateText/streamText/createOpenAI)", () => {
    const { runBoundaries } = scanTsSource(VERCEL_AI_SRC, "src/agent.ts", rules);
    const joined = runBoundaries.map((s) => s.snippet).join(" ");
    expect(runBoundaries.length).toBeGreaterThan(0);
    expect(joined).toContain("generateText");
    expect(joined).toContain("streamText");
    expect(joined).toContain("createOpenAI");
  });

  it("finds outcome sites (status setter + ORM .save()) and entity ids", () => {
    const { outcomeSites, entityIds } = scanTsSource(VERCEL_AI_SRC, "src/agent.ts", rules);
    const kinds = new Set(outcomeSites.map((s) => s.kind));
    expect(kinds.has("status_setter")).toBe(true); // ticket.status = "resolved"
    expect(kinds.has("external_write") || kinds.has("mark_function")).toBe(true); // .save()/markResolved
    expect(entityIds).toContain("conversationId");
    expect(entityIds).toContain("customerId");
    expect(entityIds).toContain("applicationId");
  });

  it("redacts a secret-shaped literal from snippets", () => {
    const { runBoundaries, outcomeSites } = scanTsSource(WITH_SECRET, "src/secret.ts", rules);
    for (const s of [...runBoundaries, ...outcomeSites]) {
      expect(s.snippet).not.toContain("REALSECRETVALUE");
      expect(s.snippet).not.toContain("sk-ant-api03-REALSECRETVALUE1234567890abcdefghij");
    }
  });

  it("marks status_setter line 1-based, like Python", () => {
    const { outcomeSites } = scanTsSource(VERCEL_AI_SRC, "src/agent.ts", rules);
    const setter = outcomeSites.find((s) => s.kind === "status_setter");
    expect(setter).toBeDefined();
    expect(setter?.line).toBeGreaterThan(0);
  });
});
