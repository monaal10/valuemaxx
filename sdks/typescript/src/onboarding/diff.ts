/**
 * Diff — the hunks-only, secret-free reviewable diff. TS mirror of Python
 * `valuemaxx.onboarding.diff`. Emits one `init()` insert per run boundary plus the generated
 * `outcomes.yaml` hunk — never whole files, so raw source can't leak through the diff. Every
 * line is redacted.
 */

import { redact } from "./redact.js";
import { renderOutcomesYaml } from "./render.js";
import type { Proposal } from "./propose.js";
import type { OnboardingRules, ScanSite } from "./types.js";

const INIT_LINE = "import valuemaxx; valuemaxx.init()  // added by the onboarding agent";

export interface DiffHunk {
  readonly file: string;
  readonly header: string;
  readonly lines: readonly string[];
}

export interface ReviewableDiff {
  readonly hunks: readonly DiffHunk[];
}

function initHunk(boundary: ScanSite, rules: OnboardingRules): DiffHunk {
  const line = boundary.line;
  return {
    file: redact(boundary.file, rules),
    header: redact(`@@ -${line},0 +${line},1 @@ ${boundary.symbol}`, rules),
    lines: [redact(`+    ${INIT_LINE}`, rules)],
  };
}

function outcomesYamlHunk(proposal: Proposal, rules: OnboardingRules): DiffHunk {
  const body = renderOutcomesYaml(proposal, rules).replace(/\n$/, "").split("\n");
  return {
    file: "outcomes.yaml",
    header: `@@ -0,0 +1,${body.length} @@`,
    lines: body.map((l) => `+${l}`),
  };
}

/** Build a hunks-only reviewable diff (additive, bounded, secret-free). */
export function buildReviewableDiff(
  scan: { runBoundaries: readonly ScanSite[] },
  proposal: Proposal,
  rules: OnboardingRules,
): ReviewableDiff {
  const hunks: DiffHunk[] = scan.runBoundaries.map((b) => initHunk(b, rules));
  hunks.push(outcomesYamlHunk(proposal, rules));
  return { hunks };
}
