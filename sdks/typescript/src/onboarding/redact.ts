/**
 * Secret redaction — the TS mirror of Python `valuemaxx.onboarding.redact`.
 *
 * Scrubs secret-shaped tokens (provider key prefixes, secret-named assignments, and
 * high-entropy credential blobs) from any snippet before it leaves the scanner, so a real
 * `.env`-adjacent literal never lands in an onboarding result. The patterns + the entropy
 * threshold come from the shared rules contract, so Python and TS scrub identically (a
 * parity test enforces it). Never executes scanned code.
 */

import type { OnboardingRules } from "./types.js";

/** Bits-per-character Shannon entropy of `token` (0 for empty) — mirrors the Python calc. */
function shannonEntropy(token: string): number {
  if (token.length === 0) return 0;
  const counts = new Map<string, number>();
  for (const ch of token) counts.set(ch, (counts.get(ch) ?? 0) + 1);
  const n = token.length;
  let bits = 0;
  for (const c of counts.values()) {
    const p = c / n;
    bits -= p * Math.log2(p);
  }
  return bits;
}

/**
 * Replace every secret-shaped token in `text` with the redaction placeholder. Order matches
 * Python: prefix patterns first (admin key before generic sk-ant), then the assignment form
 * (redacting only the value), then high-entropy blobs above the entropy threshold.
 */
export function redact(text: string, rules: OnboardingRules): string {
  let out = text;
  const placeholder = rules.redaction_placeholder;

  for (const pattern of rules.redact_prefix_patterns) {
    out = out.replace(new RegExp(pattern, "g"), placeholder);
  }

  // Assignment form: <secret-name> [:=] "<value>" — redact the captured value only. The
  // Python pattern is case-insensitive with a word-boundaried name and a 6+ char value.
  const assignment = new RegExp(
    `\\b(?:${rules.redact_secret_name_alt})\\b\\s*[:=]\\s*("[^"]{6,}"|'[^']{6,}'|[^\\s'"]{6,})`,
    "gi",
  );
  out = out.replace(assignment, (match, value: string) => match.replace(value, placeholder));

  // High-entropy blobs: a long credential-ish run, scrubbed only if its entropy clears the
  // threshold (so ordinary long identifiers/base64-looking-but-low-entropy text survives).
  const blob = new RegExp(rules.redact_high_entropy_pattern, "g");
  out = out.replace(blob, (token) =>
    shannonEntropy(token) >= rules.redact_high_entropy_bits ? placeholder : token,
  );

  return out;
}
