/**
 * Golden cross-language parity: the TS `onboard` pipeline produces the SAME proposed
 * `outcomes.yaml` (parsed) as the Python one on a shared fixture repo.
 *
 * The fixture lives at tests/wire_contract/onboarding_fixture/ and the expected parsed output
 * at tests/wire_contract/onboarding_golden.json — both generated FROM Python (the single source
 * of the pipeline semantics). This test runs the TS `onboard` on that same fixture, parses the
 * YAML it renders, and asserts deep-equality with the golden. A drift in either scanner or in
 * propose/render makes this fail, so the two pipelines can never diverge in what they PROPOSE.
 * (The contract is the parsed content — `outcomes.yaml` is consumed via yaml.safe_load — not
 * exact whitespace, which the two YAML serializers format differently.)
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { parse } from "yaml";
import { describe, expect, it } from "vitest";

import { onboard } from "../src/onboarding/onboard.js";

const FIXTURE = fileURLToPath(
  new URL("../../../tests/wire_contract/onboarding_fixture", import.meta.url),
);
const GOLDEN = fileURLToPath(
  new URL("../../../tests/wire_contract/onboarding_golden.json", import.meta.url),
);

describe("onboard cross-language parity", () => {
  it("TS onboard proposes the same outcomes.yaml (parsed) as Python", () => {
    const result = onboard(FIXTURE);
    const tsParsed = parse(result.outcomesYaml) as unknown;
    const golden = JSON.parse(readFileSync(GOLDEN, "utf8")) as unknown;
    expect(tsParsed).toEqual(golden);
  });

  it("finds a run boundary for each generateText/streamText call", () => {
    const { scan } = onboard(FIXTURE);
    // agent.ts has generateText + streamText + createAnthropic => at least 3 run boundaries.
    expect(scan.runBoundaries.length).toBeGreaterThanOrEqual(3);
  });
});
