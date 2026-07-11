/**
 * T3 run_id injection (TS) — stamp the active run_id into an outbound SDK call's args.
 *
 * The TS mirror of Python `valuemaxx.outcomes.instrument.injection`: at init() each declared
 * echoing call (e.g. `stripe.paymentIntents.create`) is wrapped so that, inside an active
 * run, the run_id is copy-on-write merged into the configured `injectInto` path of the
 * call's first-argument options object — so the external system echoes it back on its later
 * webhook (converting delayed attribution into an exact T3 join).
 *
 * Same invariants as Python: copy-on-write (the caller's own object is never mutated),
 * pass-through with no active run, a missing parent path is created, an unresolved target is
 * REPORTED (never a silent no-op), and a host error is never swallowed.
 */

import { describe, expect, it } from "vitest";

import { installRunIdInjection } from "../src/injection.js";
import { run } from "../src/run.js";

/** A stripe-like object whose `create` echoes the options it received. */
function makeClient(): {
  paymentIntents: { create: (opts: Record<string, unknown>) => Record<string, unknown> };
} {
  return {
    paymentIntents: {
      create: (opts: Record<string, unknown>) => ({ received: opts }),
    },
  };
}

describe("installRunIdInjection (T3)", () => {
  it("merges run_id into the injectInto path of the call options", () => {
    const client = makeClient();
    installRunIdInjection([
      { owner: client.paymentIntents, method: "create", injectInto: "metadata.atm_run_id" },
    ]);
    const result = run("run-7", () => client.paymentIntents.create({ amount: 100 }));
    const received = result.received as { metadata: Record<string, unknown> };
    expect(received.metadata.atm_run_id).toBe("run-7");
  });

  it("preserves pre-existing keys on the injected object (deep merge, not replace)", () => {
    const client = makeClient();
    installRunIdInjection([
      { owner: client.paymentIntents, method: "create", injectInto: "metadata.atm_run_id" },
    ]);
    const result = run("run-7", () =>
      client.paymentIntents.create({ amount: 100, metadata: { customer: "c1" } }),
    );
    const received = result.received as { metadata: Record<string, unknown> };
    expect(received.metadata.atm_run_id).toBe("run-7");
    expect(received.metadata.customer).toBe("c1");
  });

  it("is copy-on-write: the caller's own object is never mutated", () => {
    const client = makeClient();
    installRunIdInjection([
      { owner: client.paymentIntents, method: "create", injectInto: "metadata.atm_run_id" },
    ]);
    const callerMetadata = { customer: "c1" };
    run("run-7", () => client.paymentIntents.create({ amount: 100, metadata: callerMetadata }));
    expect(callerMetadata).toEqual({ customer: "c1" });
  });

  it("passes through unchanged when there is no active run", () => {
    const client = makeClient();
    installRunIdInjection([
      { owner: client.paymentIntents, method: "create", injectInto: "metadata.atm_run_id" },
    ]);
    const result = client.paymentIntents.create({ amount: 100 });
    const received = result.received as { metadata?: Record<string, unknown> };
    expect(received.metadata).toBeUndefined();
  });

  it("creates the missing parent path without touching siblings", () => {
    const client = makeClient();
    installRunIdInjection([
      { owner: client.paymentIntents, method: "create", injectInto: "metadata.atm_run_id" },
    ]);
    const result = run("run-9", () => client.paymentIntents.create({ amount: 100 }));
    const received = result.received as { metadata: Record<string, unknown>; amount: number };
    expect(received.metadata.atm_run_id).toBe("run-9");
    expect(received.amount).toBe(100);
  });

  it("reports an unresolved target (missing method) — never a silent no-op", () => {
    const owner: Record<string, unknown> = {};
    const report = installRunIdInjection([
      { owner, method: "create", injectInto: "metadata.atm_run_id" },
    ]);
    expect(report.unresolved).toHaveLength(1);
    expect(report.installed).toHaveLength(0);
  });

  it("does not swallow a host error thrown by the wrapped call", () => {
    const owner = {
      create: (): never => {
        throw new Error("stripe down");
      },
    };
    installRunIdInjection([{ owner, method: "create", injectInto: "metadata.atm_run_id" }]);
    expect(() => run("run-7", () => owner.create())).toThrowError("stripe down");
  });

  it("reports a resolved target as installed", () => {
    const client = makeClient();
    const report = installRunIdInjection([
      { owner: client.paymentIntents, method: "create", injectInto: "metadata.atm_run_id" },
    ]);
    expect(report.installed).toHaveLength(1);
    expect(report.unresolved).toHaveLength(0);
  });
});
