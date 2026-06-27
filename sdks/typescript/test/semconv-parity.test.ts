/**
 * Cross-language wire-contract parity (H3).
 *
 * The Python side is the single source of truth: it generates
 * `tests/wire_contract/semconv_keys.json` as `{"keys": sorted(ALL_KEYS)}`. This
 * test asserts the TypeScript `semconv.ts` key set is BYTE-IDENTICAL to that
 * fixture, so a span emitted by either language carries exactly the same keys.
 * If this ever drifts, the two SDKs no longer share one wire contract — that is
 * a release blocker, not a warning.
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { ALL_KEYS } from "../src/semconv.js";

const FIXTURE_URL = new URL("../../../tests/wire_contract/semconv_keys.json", import.meta.url);

interface SemconvFixture {
  readonly keys: string[];
}

function loadFixture(): SemconvFixture {
  const raw = readFileSync(fileURLToPath(FIXTURE_URL), "utf8");
  const parsed: unknown = JSON.parse(raw);
  if (
    typeof parsed !== "object" ||
    parsed === null ||
    !Array.isArray((parsed as { keys?: unknown }).keys)
  ) {
    throw new Error("semconv_keys.json is malformed: expected { keys: string[] }");
  }
  return parsed as SemconvFixture;
}

describe("semconv wire-contract parity", () => {
  it("the TS key set is byte-identical to the frozen Python fixture", () => {
    const fixture = loadFixture();
    // The fixture is the authoritative sorted list; ALL_KEYS is sorted too, so a
    // deep-equal on the arrays is the byte-for-byte contract.
    expect([...ALL_KEYS]).toEqual(fixture.keys);
  });

  it("emits exactly the fixture keys — no extras, none missing", () => {
    const fixture = loadFixture();
    expect(new Set(ALL_KEYS)).toEqual(new Set(fixture.keys));
    expect(ALL_KEYS.length).toBe(fixture.keys.length);
  });

  it("the key set is sorted (matches the fixture's sort order)", () => {
    const sorted = [...ALL_KEYS].sort();
    expect([...ALL_KEYS]).toEqual(sorted);
  });

  it("contains both the gen_ai.* standard keys and the ai_margin.* extensions", () => {
    expect(ALL_KEYS).toContain("gen_ai.usage.input_tokens");
    expect(ALL_KEYS).toContain("gen_ai.usage.output_tokens");
    expect(ALL_KEYS).toContain("ai_margin.usage.cache_read_tokens");
    expect(ALL_KEYS).toContain("ai_margin.usage.cache_write_5m_tokens");
    expect(ALL_KEYS).toContain("ai_margin.usage.cache_write_1h_tokens");
    expect(ALL_KEYS).toContain("ai_margin.usage.reasoning_tokens");
    expect(ALL_KEYS).toContain("ai_margin.run_id");
    expect(ALL_KEYS).toContain("ai_margin.tenant_id");
    expect(ALL_KEYS).toContain("ai_margin.cost_usd");
    expect(ALL_KEYS).toContain("ai_margin.is_streaming");
    expect(ALL_KEYS).toContain("ai_margin.partial_recovered");
  });
});
