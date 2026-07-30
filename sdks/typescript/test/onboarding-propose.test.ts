/**
 * Onboarding propose/walk filters — the rules that keep a real-repo scan REVIEWABLE.
 *
 * A scan of a production repo proposed 4,058 rules before these filters: 57% named
 * `<module>` (unbindable) and 63% from test files (a test's `markCompleted()` is a fake).
 * Nobody reviews 4,000 rules, so an unreviewable proposal is the same as no proposal —
 * these tests pin the two filters that make the output usable.
 */

import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import rulesJson from "../src/onboarding/onboarding_rules.json" with { type: "json" };
import { onboard, scanCodebase } from "../src/onboarding/onboard.js";
import { buildProposal } from "../src/onboarding/propose.js";
import type { OnboardingRules, ScanSite } from "../src/onboarding/types.js";

const rules = rulesJson as OnboardingRules;

function site(overrides: Partial<ScanSite> = {}): ScanSite {
  return {
    kind: "mark_function",
    file: "src/a.ts",
    line: 1,
    symbol: "markCompleted",
    snippet: "markCompleted(job)",
    system: null,
    echoesMetadata: false,
    entityIds: [],
    ...overrides,
  };
}

/** Build a throwaway repo tree; returns its root. */
function makeRepo(files: Record<string, string>): string {
  const root = mkdtempSync(join(tmpdir(), "vmx-onboard-"));
  for (const [rel, body] of Object.entries(files)) {
    const full = join(root, rel);
    mkdirSync(join(full, ".."), { recursive: true });
    writeFileSync(full, body);
  }
  return root;
}

describe("buildProposal — module-scope filter", () => {
  it("drops a site at module scope (no named function to bind to)", () => {
    const proposal = buildProposal(
      {
        outcomeSites: [site({ symbol: rules.module_symbol }), site({ symbol: "markApproved" })],
        entityIds: [],
        warnings: [],
      },
      rules,
    );
    expect(proposal.rules).toHaveLength(1);
    expect(proposal.rules[0]?.name).toBe("markApproved");
  });

  it("warns about what it dropped rather than silently shrinking the proposal", () => {
    const proposal = buildProposal(
      {
        outcomeSites: [
          site({ symbol: rules.module_symbol }),
          site({ symbol: rules.module_symbol }),
        ],
        entityIds: [],
        warnings: [],
      },
      rules,
    );
    expect(proposal.rules).toHaveLength(0);
    expect(proposal.warnings.join(" ")).toContain("2 outcome site(s) were skipped");
  });
});

describe("scanCodebase — test/fixture exclusion", () => {
  it("skips test files and test directories, keeps production source", () => {
    const root = makeRepo({
      "src/agent.ts": `export async function go() { return generateText({ prompt: "x" }); }`,
      "src/agent.test.ts": `export async function go() { return generateText({ prompt: "x" }); }`,
      "src/agent.spec.ts": `export async function go() { return generateText({ prompt: "x" }); }`,
      "tests/helper.ts": `export async function go() { return generateText({ prompt: "x" }); }`,
      "src/__mocks__/m.ts": `export async function go() { return generateText({ prompt: "x" }); }`,
    });
    const files = scanCodebase(root).runBoundaries.map((s) => s.file);
    expect(files).toContain("src/agent.ts");
    expect(files.join(" ")).not.toContain(".test.");
    expect(files.join(" ")).not.toContain(".spec.");
    expect(files.join(" ")).not.toContain("tests/");
    expect(files.join(" ")).not.toContain("__mocks__");
  });

  it("does not mistake a production file whose name merely contains a test word", () => {
    const root = makeRepo({
      "src/latest.ts": `export async function go() { return generateText({ prompt: "x" }); }`,
      "src/contest.ts": `export async function go() { return generateText({ prompt: "x" }); }`,
    });
    const files = scanCodebase(root).runBoundaries.map((s) => s.file);
    expect(files).toContain("src/latest.ts");
    expect(files).toContain("src/contest.ts");
  });

  it("proposes no rule from a repo that is only tests", () => {
    const root = makeRepo({
      "src/a.test.ts": `export async function go() { await markCompleted(job); }`,
      "tests/b.ts": `export async function go() { await markCompleted(job); }`,
    });
    expect(onboard(root).proposal.rules).toHaveLength(0);
  });
});
