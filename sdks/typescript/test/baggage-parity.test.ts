/**
 * Cross-language T2 baggage-encoding parity: the TS producer emits the BYTE-IDENTICAL
 * `baggage` header the Python producer does, for the same input vectors.
 *
 * The two T2 producers are the same mechanism in each language's native wrap/context API.
 * This pins that: the shared vectors (defined identically here and in the Python generator
 * `tests/wire_contract/generate_baggage_parity_golden.py`) are driven through the TS producer
 * and each emitted `baggage` string is asserted equal to the Python-generated golden. A drift
 * in EITHER producer's encoding (order, separators, stale-key replacement, the key itself)
 * fails this test. The golden's keyset must also match the vectors — so a vector added on only
 * one side is caught too.
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { installRunIdBaggage } from "../src/baggage.js";
import { run } from "../src/run.js";

const GOLDEN = fileURLToPath(
  new URL("../../../tests/wire_contract/baggage_parity_golden.json", import.meta.url),
);

/** The shared vectors — MUST mirror VECTORS in the Python generator (same names, run_ids, headers). */
const VECTORS: ReadonlyArray<{
  name: string;
  runId: string;
  headers: Record<string, string>;
}> = [
  { name: "no_headers", runId: "run-1", headers: {} },
  { name: "empty_baggage", runId: "run-2", headers: { baggage: "" } },
  { name: "existing_member", runId: "run-3", headers: { baggage: "team=payments" } },
  { name: "multiple_members", runId: "run-4", headers: { baggage: "team=payments,region=us" } },
  {
    name: "stale_run_id_replaced",
    runId: "run-5",
    headers: { baggage: "valuemaxx.run_id=stale,team=x" },
  },
  { name: "unrelated_headers_only", runId: "run-6", headers: { authorization: "Bearer x" } },
];

/** Drive one vector through the REAL TS producer; return the emitted baggage string. */
function baggageFor(runId: string, headers: Record<string, string>): string {
  const probe = { request: (opts: Record<string, unknown>) => ({ received: opts }) };
  installRunIdBaggage([{ owner: probe, method: "request" }]);
  const result = run(runId, () => probe.request({ url: "u", headers: { ...headers } })) as {
    received: { headers: Record<string, string> };
  };
  const baggage = result.received.headers.baggage;
  expect(baggage).toBeDefined(); // the producer must have set it inside an active run.
  return baggage as string;
}

describe("baggage cross-language parity", () => {
  const golden = JSON.parse(readFileSync(GOLDEN, "utf8")) as Record<string, string>;

  it("TS producer emits the same baggage string as Python for every vector", () => {
    const tsOutput: Record<string, string> = {};
    for (const v of VECTORS) {
      tsOutput[v.name] = baggageFor(v.runId, v.headers);
    }
    expect(tsOutput).toEqual(golden);
  });

  it("the vector set matches the golden's keyset (no one-sided vector drift)", () => {
    expect(new Set(VECTORS.map((v) => v.name))).toEqual(new Set(Object.keys(golden)));
  });
});
