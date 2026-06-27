/**
 * Startup version self-test: warn loudly + degrade, never silent (§5.2, H9).
 *
 * Mirrors the Python `packages/capture/tests/test_selftest.py` behavior: an
 * out-of-range version or a missing hook degrades capture to `per_call` with a
 * warning that NAMES the offending package/version — never a silent wrong
 * granularity.
 */

import { describe, expect, it, vi } from "vitest";

import { rangeContains, versionSelftest } from "../src/selftest.js";

describe("versionSelftest", () => {
  it("stays per_attempt for in-range versions with the hook present", () => {
    const result = versionSelftest({
      installedVersions: { openai: "4.104.0", "@anthropic-ai/sdk": "0.40.0" },
      hookPresent: true,
    });
    expect(result.granularity).toBe("per_attempt");
    expect(result.warnings).toHaveLength(0);
  });

  it("degrades to per_call and names the package/version when out of range", () => {
    const logger = { warn: vi.fn() };
    const result = versionSelftest({
      installedVersions: { openai: "99.0.0" },
      hookPresent: true,
      logger,
    });
    expect(result.granularity).toBe("per_call");
    expect(result.warnings.join(" ")).toContain("openai 99.0.0");
    expect(logger.warn).toHaveBeenCalled();
  });

  it("degrades to per_call and warns when the hook is absent", () => {
    const result = versionSelftest({ installedVersions: {}, hookPresent: false });
    expect(result.granularity).toBe("per_call");
    expect(result.warnings.join(" ")).toMatch(/hook did not take effect/);
  });

  it("skips packages it has no range for (not an error)", () => {
    const result = versionSelftest({
      installedVersions: { "some-other-lib": "1.2.3" },
      hookPresent: true,
    });
    expect(result.granularity).toBe("per_attempt");
    expect(result.warnings).toHaveLength(0);
  });
});

describe("rangeContains", () => {
  const range = { floor: "4.0.0", ceiling: "6.0.0", knownGoodExample: "4.104.0" };

  it("is inclusive of the floor, exclusive of the ceiling", () => {
    expect(rangeContains(range, "4.0.0")).toBe(true);
    expect(rangeContains(range, "5.9.9")).toBe(true);
    expect(rangeContains(range, "6.0.0")).toBe(false);
    expect(rangeContains(range, "3.9.9")).toBe(false);
  });

  it("tolerates rc/dev suffixes by truncating at the first non-digit", () => {
    expect(rangeContains(range, "4.1.0-beta.2")).toBe(true);
  });
});
