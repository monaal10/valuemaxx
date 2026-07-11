/**
 * T2 baggage producer (TS) — carry the active run_id across a live hop on W3C baggage.
 *
 * The TS mirror of Python `valuemaxx.outcomes.instrument.baggage`: at init() each declared
 * outbound HTTP call is wrapped so that, inside an active run, the run_id is copy-on-write
 * merged as a `valuemaxx.run_id=<id>` member of the outbound `baggage` header. The receiving
 * service parses it back and the cascade binds `exact` (T2). The key comes from the shared
 * wire contract (`run_id_wire.json`), so Python and TS stamp the identical key.
 *
 * Same invariants as the T3 injector: copy-on-write headers, list-merge (existing members
 * preserved, our key never duplicated), pass-through with no active run, unresolved target
 * reported, host error never swallowed.
 */

import { describe, expect, it } from "vitest";

import { installRunIdBaggage } from "../src/baggage.js";
import { run } from "../src/run.js";
import wire from "../src/run_id_wire.json" with { type: "json" };

const KEY = wire.baggage_run_id_key;

/** An http-like client whose `request` echoes the options (incl. headers) it received. */
function makeClient(): {
  request: (opts: Record<string, unknown>) => Record<string, unknown>;
} {
  return { request: (opts: Record<string, unknown>) => ({ received: opts }) };
}

function headersOf(result: Record<string, unknown>): Record<string, string> {
  const received = result.received as { headers?: Record<string, string> };
  return received.headers ?? {};
}

/** The baggage header value, asserted present (the producer must have set it). */
function baggageOf(result: Record<string, unknown>): string {
  const value = headersOf(result).baggage;
  expect(value).toBeDefined();
  return value as string;
}

describe("installRunIdBaggage (T2)", () => {
  it("stamps run_id onto the baggage header of the outbound call", () => {
    const client = makeClient();
    installRunIdBaggage([{ owner: client, method: "request" }]);
    const result = run("run-7", () => client.request({ url: "u" }));
    expect(headersOf(result).baggage).toBe(`${KEY}=run-7`);
  });

  it("preserves existing baggage members (W3C list-merge)", () => {
    const client = makeClient();
    installRunIdBaggage([{ owner: client, method: "request" }]);
    const result = run("run-7", () =>
      client.request({ url: "u", headers: { baggage: "team=payments" } }),
    );
    const members = new Set(baggageOf(result).split(","));
    expect(members).toEqual(new Set(["team=payments", `${KEY}=run-7`]));
  });

  it("replaces a stale run_id member rather than duplicating it", () => {
    const client = makeClient();
    installRunIdBaggage([{ owner: client, method: "request" }]);
    const result = run("run-9", () =>
      client.request({ url: "u", headers: { baggage: `${KEY}=stale,team=x` } }),
    );
    const members = baggageOf(result).split(",");
    const ours = members.filter((m) => m.startsWith(`${KEY}=`));
    expect(ours).toEqual([`${KEY}=run-9`]);
    expect(members).toContain("team=x");
  });

  it("is copy-on-write: the caller's own headers object is never mutated", () => {
    const client = makeClient();
    installRunIdBaggage([{ owner: client, method: "request" }]);
    const callerHeaders = { authorization: "Bearer x" };
    run("run-7", () => client.request({ url: "u", headers: callerHeaders }));
    expect(callerHeaders).toEqual({ authorization: "Bearer x" });
  });

  it("passes through unchanged when there is no active run", () => {
    const client = makeClient();
    installRunIdBaggage([{ owner: client, method: "request" }]);
    const result = client.request({ url: "u", headers: { authorization: "Bearer x" } });
    expect(headersOf(result).baggage).toBeUndefined();
  });

  it("reports an unresolved target (missing method) — never silent", () => {
    const owner: Record<string, unknown> = {};
    const report = installRunIdBaggage([{ owner, method: "request" }]);
    expect(report.unresolved).toHaveLength(1);
    expect(report.installed).toHaveLength(0);
  });

  it("does not swallow a host error thrown by the wrapped call", () => {
    const owner = {
      request: (): never => {
        throw new Error("network down");
      },
    };
    installRunIdBaggage([{ owner, method: "request" }]);
    expect(() => run("run-7", () => owner.request())).toThrowError("network down");
  });
});
