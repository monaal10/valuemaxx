/**
 * Onboard orchestrator — scan a repo → propose → render `outcomes.yaml` → reviewable diff.
 * The TS mirror of the Python `valuemaxx onboard` pipeline; a golden parity test asserts the
 * two produce the same proposal + rendered outcomes on the same fixture repo.
 *
 * Read-only: it never executes scanned code and never writes files — the diff is printed for a
 * human to review (rules stay UNCONFIRMED), exactly like the Python CLI.
 */

import { readFileSync, readdirSync, statSync } from "node:fs";
import { extname, join, relative } from "node:path";

import { buildReviewableDiff, type ReviewableDiff } from "./diff.js";
import { buildProposal, type Proposal } from "./propose.js";
import { renderOutcomesYaml } from "./render.js";
import rulesJson from "./onboarding_rules.json" with { type: "json" };
import { scanTsSource } from "./scan.js";
import type { OnboardingRules, ScanResult, ScanSite } from "./types.js";

const RULES = rulesJson as OnboardingRules;

/** Walk `root` for TS/JS source files, skipping ignored + dot directories (like Python). */
function iterSourceFiles(root: string): string[] {
  const suffixes = new Set(RULES.ts_suffixes);
  const ignored = new Set(RULES.ignored_dirs);
  const out: string[] = [];
  const walk = (dir: string): void => {
    let entries: string[];
    try {
      entries = readdirSync(dir);
    } catch {
      return; // unreadable dir — skip, never throw
    }
    for (const entry of entries) {
      const full = join(dir, entry);
      let st;
      try {
        st = statSync(full);
      } catch {
        continue;
      }
      if (st.isDirectory()) {
        if (ignored.has(entry) || entry.startsWith(".")) continue;
        walk(full);
      } else if (suffixes.has(extname(entry))) {
        out.push(full);
      }
    }
  };
  walk(root);
  return out.sort(); // deterministic file order
}

/** Scan an entire repo. Returns the aggregate `ScanResult` (run boundaries + outcome sites). */
export function scanCodebase(root: string): ScanResult {
  const runBoundaries: ScanSite[] = [];
  const outcomeSites: ScanSite[] = [];
  const entityIds: string[] = [];
  const warnings: string[] = [];

  for (const file of iterSourceFiles(root)) {
    const rel = relative(root, file);
    let text: string;
    try {
      text = readFileSync(file, "utf8");
    } catch {
      continue;
    }
    const result = scanTsSource(text, rel, RULES);
    runBoundaries.push(...result.runBoundaries);
    outcomeSites.push(...result.outcomeSites);
    for (const id of result.entityIds) if (!entityIds.includes(id)) entityIds.push(id);
  }

  return { runBoundaries, outcomeSites, entityIds, warnings };
}

export interface OnboardResult {
  readonly scan: ScanResult;
  readonly proposal: Proposal;
  readonly outcomesYaml: string;
  readonly diff: ReviewableDiff;
}

/** Run the full onboarding pipeline against a repo root (read-only; nothing written). */
export function onboard(root: string): OnboardResult {
  const scan = scanCodebase(root);
  const proposal = buildProposal(scan, RULES);
  const outcomesYaml = renderOutcomesYaml(proposal, RULES);
  const diff = buildReviewableDiff(scan, proposal, RULES);
  return { scan, proposal, outcomesYaml, diff };
}

/** Render the onboard result as the reviewable text the CLI prints. */
export function renderOnboard(result: OnboardResult): string {
  const lines: string[] = [];
  lines.push("# --- proposed outcomes.yaml ---");
  lines.push(result.outcomesYaml.replace(/\n$/, ""));
  lines.push("# --- reviewable diff ---");
  for (const hunk of result.diff.hunks) {
    lines.push(`--- ${hunk.file}`);
    lines.push(`+++ ${hunk.file}`);
    lines.push(hunk.header);
    lines.push(...hunk.lines);
  }
  lines.push("");
  lines.push("onboard: candidate outcome rules are UNCONFIRMED until you review the diff.");
  return lines.join("\n");
}
