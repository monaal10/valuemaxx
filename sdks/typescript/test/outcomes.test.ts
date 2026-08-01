/**
 * Declarative outcome instrumentation — the runtime half of `outcomes.yaml`.
 *
 * Before this existed, `valuemaxx onboard` rendered an outcomes file that nothing ever
 * read: neither SDK loaded one, so a declared outcome fired nothing and
 * cost-per-outcome was unreachable however carefully the file was written. These tests
 * pin the behaviors that make a declared outcome trustworthy — it fires on success,
 * NOT on failure, it carries the ambient run id (what earns the `exact` tier), it
 * never breaks the host, and a rule that matches nothing is reported rather than
 * silently doing nothing.
 */

import { describe, expect, it, vi } from "vitest";

import { installOutcomes, type OutcomesDocument, recordOutcomeNow } from "../src/outcomes.js";
import { run } from "../src/run.js";

const CONFIG = {
  tenantId: "6f1c3b2a-0000-4a00-8000-000000000001",
  ingestKey: "dev",
  endpoint: "http://127.0.0.1:8000",
  newId: () => "oe_test",
  now: () => new Date("2026-07-30T12:00:00.000Z"),
} as const;

const DOC: OutcomesDocument = {
  outcomes: [{ name: "alt_created", match_target: "src/alts.ts:markAltCreated" }],
};

function okFetch(): { fetchImpl: typeof fetch; calls: unknown[] } {
  const calls: unknown[] = [];
  const fetchImpl = vi.fn((_url: unknown, init: unknown) => {
    calls.push(JSON.parse((init as { body: string }).body));
    return Promise.resolve({ ok: true, status: 200 } as Response);
  }) as unknown as typeof fetch;
  return { fetchImpl, calls };
}

/** The recorder is fire-and-forget, so let its microtask + promise chain settle. */
const settle = async (): Promise<void> => {
  await new Promise((r) => setTimeout(r, 0));
};

describe("installOutcomes", () => {
  it("records the outcome when the named function is called", async () => {
    const { fetchImpl, calls } = okFetch();
    const targets = { markAltCreated: (id: string) => `made ${id}` };
    installOutcomes(DOC, targets, { ...CONFIG, fetchImpl });

    expect(targets.markAltCreated("alt_1")).toBe("made alt_1");
    await settle();

    expect(calls).toHaveLength(1);
    expect((calls[0] as { name: string }).name).toBe("alt_created");
  });

  it("carries the ambient run id — this is what earns the `exact` binding tier", async () => {
    const { fetchImpl, calls } = okFetch();
    const targets = { markAltCreated: () => "ok" };
    installOutcomes(DOC, targets, { ...CONFIG, fetchImpl });

    run("build-alt-42", () => targets.markAltCreated());
    await settle();

    expect((calls[0] as { binding: { run_id: string } }).binding.run_id).toBe("build-alt-42");
  });

  it("leaves the tier null so the backend cascade decides it", async () => {
    const { fetchImpl, calls } = okFetch();
    const targets = { markAltCreated: () => "ok" };
    installOutcomes(DOC, targets, { ...CONFIG, fetchImpl });

    targets.markAltCreated();
    await settle();

    // A caller must never be able to promote its own outcome to a billing-grade tier.
    const binding = (calls[0] as { binding: { tier: null; bound_by: null } }).binding;
    expect(binding.tier).toBeNull();
    expect(binding.bound_by).toBeNull();
  });

  it("does NOT record when the function throws — a failure is not an outcome", async () => {
    const { fetchImpl, calls } = okFetch();
    const targets = {
      markAltCreated: () => {
        throw new Error("boom");
      },
    };
    installOutcomes(DOC, targets, { ...CONFIG, fetchImpl });

    expect(() => targets.markAltCreated()).toThrow("boom");
    await settle();
    expect(calls).toHaveLength(0);
  });

  it("does NOT record when an async function rejects", async () => {
    const { fetchImpl, calls } = okFetch();
    const targets = { markAltCreated: () => Promise.reject(new Error("nope")) };
    installOutcomes(DOC, targets, { ...CONFIG, fetchImpl });

    await expect(targets.markAltCreated()).rejects.toThrow("nope");
    await settle();
    expect(calls).toHaveLength(0);
  });

  it("records an async outcome only after it resolves", async () => {
    const { fetchImpl, calls } = okFetch();
    const targets = { markAltCreated: () => Promise.resolve("done") };
    installOutcomes(DOC, targets, { ...CONFIG, fetchImpl });

    await targets.markAltCreated();
    await settle();
    expect(calls).toHaveLength(1);
  });

  // Cost instrumentation must never turn a working feature into a broken one.
  it("never breaks the host when the backend is down", async () => {
    const failing = (() => Promise.reject(new Error("ECONNREFUSED"))) as unknown as typeof fetch;
    const warn = vi.fn();
    const targets = { markAltCreated: () => "still works" };
    installOutcomes(DOC, targets, {
      ...CONFIG,
      fetchImpl: failing,
      logger: { warn, error: vi.fn() },
    });

    expect(targets.markAltCreated()).toBe("still works");
    await settle();
    expect(warn).toHaveBeenCalled();
  });

  it("reports a rule that matches no function rather than silently doing nothing", () => {
    const warn = vi.fn();
    const result = installOutcomes(
      { outcomes: [{ name: "ghost", match_target: "src/x.ts:doesNotExist" }] },
      {},
      { ...CONFIG, fetchImpl: okFetch().fetchImpl, logger: { warn, error: vi.fn() } },
    );
    // A declared outcome that never fires is indistinguishable from one that never
    // happened — so an unresolvable rule has to be loud.
    expect(result.unresolved).toEqual(["ghost -> doesNotExist"]);
    expect(warn).toHaveBeenCalled();
  });

  it("restores the original function so instrumentation is reversible", async () => {
    const { fetchImpl, calls } = okFetch();
    const original = (): string => "raw";
    const targets: Record<string, unknown> = { markAltCreated: original };
    const { handles } = installOutcomes(DOC, targets, { ...CONFIG, fetchImpl });

    for (const h of handles) h.restore();
    expect(targets.markAltCreated).toBe(original);

    (targets.markAltCreated as () => string)();
    await settle();
    expect(calls).toHaveLength(0);
  });
});

describe("recordOutcomeNow", () => {
  it("records an outcome from a call site that owns no patchable function", async () => {
    // The monkey-patch path needs a mutable object holding a named function. A
    // workflow step, a queue consumer, and a chat completion all reach their
    // "done" moment as a RETURN VALUE inside a closure — there is nothing to
    // patch, so `installOutcomes` cannot express them at all. Without a direct
    // call, every such host can bind runs and still never record the outcome
    // those runs exist to explain, leaving cost-per-outcome null forever.
    const { fetchImpl, calls } = okFetch();

    await run("build-alt-7", { entityKeys: { alt_id: "alt_7" } }, async () => {
      await recordOutcomeNow({ name: "alt_created" }, { ...CONFIG, fetchImpl });
    });

    expect(calls).toHaveLength(1);
    const body = calls[0] as {
      name: string;
      binding: { run_id: string; tier: null };
      entity_keys: ReadonlyArray<readonly [string, string]>;
    };
    expect(body.name).toBe("alt_created");
    expect(body.binding.run_id).toBe("build-alt-7");
    // The caller never states a tier — the backend cascade owns it.
    expect(body.binding.tier).toBeNull();
    expect(body.entity_keys).toEqual([["alt_id", "alt_7"]]);
  });

  it("carries the ambient entity keys, so a unit can span several runs", async () => {
    // Entity keys are what let "cost per candidate" join a build run to a screen
    // run. They were declared on `run()` and then dropped on the floor here, so
    // the rollup they exist for was unreachable — and they cannot be backfilled.
    const { fetchImpl, calls } = okFetch();

    await run("screen-9", { entityKeys: { candidate_id: "c_9", org_id: "o_1" } }, async () => {
      await recordOutcomeNow({ name: "screened" }, { ...CONFIG, fetchImpl });
    });

    const body = calls[0] as { entity_keys: ReadonlyArray<readonly [string, string]> };
    expect(new Map(body.entity_keys)).toEqual(
      new Map([
        ["candidate_id", "c_9"],
        ["org_id", "o_1"],
      ]),
    );
  });

  it("records outside any run, binding no run rather than throwing", async () => {
    const { fetchImpl, calls } = okFetch();
    await recordOutcomeNow({ name: "orphan" }, { ...CONFIG, fetchImpl });
    const body = calls[0] as { binding: { run_id: null }; entity_keys: readonly unknown[] };
    expect(body.binding.run_id).toBeNull();
    expect(body.entity_keys).toEqual([]);
  });
});
