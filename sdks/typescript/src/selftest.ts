/**
 * Startup version self-test: warn loudly + degrade, never silent (§5.2, H9).
 *
 * Per-attempt capture requires wrapping the Node client's request path. If the
 * installed `openai`/`@anthropic-ai/sdk`/`ai` version is outside the tested
 * range, or the instrumentation hook did not take effect, we must NOT silently
 * capture the wrong granularity. Instead we **warn loudly, naming the package
 * and version**, and gracefully **degrade to `per_call`** capture (tagged on
 * every emitted span).
 *
 * `versionSelftest` is pure and injectable (the installed versions + hook flag
 * are passed in) so it is deterministic under test. Mirrors the Python
 * `valuemaxx.capture.selftest`.
 */

/** Whether per-attempt capture is in effect, or the degraded per-call fallback. */
export type CaptureGranularity = "per_attempt" | "per_call";

/** Parse a dotted version into a comparable numeric tuple (best-effort, lenient). */
function parseVersion(version: string): number[] {
  const parts: number[] = [];
  for (const segment of version.split(".")) {
    let digits = "";
    for (const ch of segment) {
      if (ch >= "0" && ch <= "9") {
        digits += ch;
      } else {
        break;
      }
    }
    if (digits === "") {
      break;
    }
    parts.push(Number.parseInt(digits, 10));
  }
  return parts;
}

/** Compare two parsed version tuples lexicographically; missing segments are 0. */
function compareVersions(a: number[], b: number[]): number {
  const len = Math.max(a.length, b.length);
  for (let i = 0; i < len; i += 1) {
    const ai = a[i] ?? 0;
    const bi = b[i] ?? 0;
    if (ai !== bi) {
      return ai < bi ? -1 : 1;
    }
  }
  return 0;
}

/** An inclusive-floor / exclusive-ceiling supported version window for a package. */
export interface SupportedRange {
  readonly floor: string;
  readonly ceiling: string;
  readonly knownGoodExample: string;
}

/** True if `version` is in [floor, ceiling). */
export function rangeContains(range: SupportedRange, version: string): boolean {
  const v = parseVersion(version);
  return (
    compareVersions(parseVersion(range.floor), v) <= 0 &&
    compareVersions(v, parseVersion(range.ceiling)) < 0
  );
}

/**
 * The tested-compatible ranges. Conservative windows we have an instrumentation
 * hook for; outside them we degrade to per_call rather than guess. Keyed by the
 * Node package name as it appears in the host's dependency tree.
 */
export const KNOWN_GOOD: Readonly<Record<string, SupportedRange>> = Object.freeze({
  openai: { floor: "4.0.0", ceiling: "6.0.0", knownGoodExample: "4.104.0" },
  "@anthropic-ai/sdk": { floor: "0.30.0", ceiling: "1.0.0", knownGoodExample: "0.40.0" },
  ai: { floor: "3.0.0", ceiling: "6.0.0", knownGoodExample: "4.0.0" },
});

/** The outcome of the startup self-test: the effective granularity + any warnings. */
export interface SelfTestResult {
  readonly granularity: CaptureGranularity;
  readonly warnings: readonly string[];
}

/**
 * Check installed versions + hook presence; degrade to per_call on any problem.
 *
 * `installedVersions` maps package name -> version string for the SDKs actually
 * present in the host (absent packages are simply skipped — not an error).
 * Every warning names the offending package and version (or the missing hook)
 * so the degrade is never silent. The optional `logger` receives each warning.
 */
export function versionSelftest(args: {
  installedVersions: Readonly<Record<string, string>>;
  hookPresent: boolean;
  logger?: Pick<Console, "warn"> | undefined;
}): SelfTestResult {
  const warnings: string[] = [];
  for (const [pkg, version] of Object.entries(args.installedVersions)) {
    const range = KNOWN_GOOD[pkg];
    if (range === undefined) {
      continue;
    }
    if (!rangeContains(range, version)) {
      warnings.push(
        `${pkg} ${version} is outside the tested range ` +
          `[${range.floor}, ${range.ceiling}); degrading capture to per_call`,
      );
    }
  }
  if (!args.hookPresent) {
    warnings.push(
      "instrumentation hook did not take effect (the patch is ineffective); " +
        "degrading capture to per_call — capture is NOT silently empty",
    );
  }
  const granularity: CaptureGranularity = warnings.length === 0 ? "per_attempt" : "per_call";
  const logger = args.logger;
  if (logger !== undefined) {
    for (const w of warnings) {
      logger.warn(`valuemaxx capture self-test: ${w}`);
    }
  }
  return { granularity, warnings };
}
