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

  // An outcome stem must be a verb applied to an object. Without this, `close()` on a DB
  // lease and `resolve()` on a Promise become CONFIRMED business outcomes — the exact
  // honesty violation the binding tiers exist to prevent.
  it("does NOT treat a bare stem or a lowercase continuation as an outcome", () => {
    const src = `
export async function handler(db: Db, deferred: Deferred) {
  await db.close();
  deferred.resolve();
  const marker = makeMarker();
  markdown(marker);
  completes(marker);
}
`;
    const { outcomeSites } = scanTsSource(src, "src/noise.ts", rules);
    expect(outcomeSites.filter((s) => s.kind === "mark_function")).toHaveLength(0);
  });

  it("treats verb+Object and verb_object as outcome transitions", () => {
    const src = `
export async function handler(job: Job) {
  await markCompleted(job);
  await mark_approved(job);
  await finalizeTurn(job);
}
`;
    const { outcomeSites } = scanTsSource(src, "src/real.ts", rules);
    const marks = outcomeSites.filter((s) => s.kind === "mark_function");
    expect(marks).toHaveLength(3);
  });

  // A long kebab-case path is 40+ chars of [A-Za-z0-9_-] and scores ~4.1 bits — above the
  // entropy threshold. Scrubbing it destroyed the match_target of every rule in a deeply
  // nested repo, so `/` must stay out of the high-entropy character class.
  it("does not redact a long nested file path as if it were a secret", () => {
    const deep = "src/workflows/complete-submission/steps/capture-and-store/index.ts";
    const src = `export async function go() { return generateText({ prompt: "x" }); }`;
    const { runBoundaries } = scanTsSource(src, deep, rules);
    expect(runBoundaries.length).toBeGreaterThan(0);
    for (const s of runBoundaries) expect(s.file).toBe(deep);
  });
});
