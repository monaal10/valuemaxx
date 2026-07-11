/**
 * init() wires the T2 baggage producer + T3 run_id injection (TS parity with Python).
 *
 * Mirrors `sdks/python/tests/test_init_run_id_carry.py`: init() accepts declared
 * `runIdInjectionTargets` (T3) and `baggageTargets` (T2), installs them, and surfaces an
 * unresolved target as a named warning — never a silent no-op. Both are fail-open.
 */

import { describe, expect, it } from "vitest";

import { init } from "../src/init.js";
import { run } from "../src/run.js";
import wire from "../src/run_id_wire.json" with { type: "json" };

const KEY = wire.baggage_run_id_key;

function baseOptions() {
  return { tenantId: "t1", ingestKey: "k", endpoint: "https://x.example" } as const;
}

describe("init() run_id carry wiring", () => {
  it("installs T3 injection targets so run_id round-trips", () => {
    const client = { create: (o: Record<string, unknown>) => ({ received: o }) };
    init({
      ...baseOptions(),
      runIdInjectionTargets: [
        { owner: client, method: "create", injectInto: "metadata.atm_run_id" },
      ],
    });
    const result = run("run-3", () => client.create({ amount: 1 })) as {
      received: { metadata: Record<string, unknown> };
    };
    expect(result.received.metadata.atm_run_id).toBe("run-3");
  });

  it("installs T2 baggage targets so run_id rides baggage", () => {
    const client = { request: (o: Record<string, unknown>) => ({ received: o }) };
    init({ ...baseOptions(), baggageTargets: [{ owner: client, method: "request" }] });
    const result = run("run-5", () => client.request({ url: "u" })) as {
      received: { headers: Record<string, string> };
    };
    expect(result.received.headers.baggage).toBe(`${KEY}=run-5`);
  });

  it("warns (named) on an unresolved injection target", () => {
    const owner: Record<string, unknown> = {};
    const result = init({
      ...baseOptions(),
      runIdInjectionTargets: [{ owner, method: "create", injectInto: "metadata.atm_run_id" }],
    });
    expect(result.warnings.some((w) => w.includes("create"))).toBe(true);
  });

  it("warns (named) on an unresolved baggage target", () => {
    const owner: Record<string, unknown> = {};
    const result = init({ ...baseOptions(), baggageTargets: [{ owner, method: "request" }] });
    expect(result.warnings.some((w) => w.includes("request"))).toBe(true);
  });

  it("omitting both leaves init() behaviour unchanged", () => {
    const result = init(baseOptions());
    expect(result.warnings).toBeDefined();
  });
});
