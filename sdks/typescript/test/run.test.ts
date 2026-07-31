/**
 * run() — ambient run_id binding via AsyncLocalStorage (H2).
 *
 * Mirrors the Python `sdks/python/tests/test_track.py`: the run id binds for the
 * duration of the call (including across awaited async work), restores the prior
 * value on exit (even on throw), and nests correctly without leaking.
 */

import { describe, expect, it } from "vitest";

import { activeAgentName, activeRunId, run, track } from "../src/run.js";

describe("run()", () => {
  it("binds the run id for the duration of the call", () => {
    expect(activeRunId()).toBeUndefined();
    const inner = run("r1", () => activeRunId());
    expect(inner).toBe("r1");
    expect(activeRunId()).toBeUndefined(); // restored after the call
  });

  it("propagates the run id across awaited async work", async () => {
    const seen = await run("async-run", async () => {
      await Promise.resolve();
      return activeRunId();
    });
    expect(seen).toBe("async-run");
  });

  it("restores the prior run id even when the body throws", () => {
    run("outer", () => {
      expect(() =>
        run("inner", () => {
          throw new Error("boom");
        }),
      ).toThrowError("boom");
      // the inner frame is gone; outer is restored, not leaked.
      expect(activeRunId()).toBe("outer");
    });
    expect(activeRunId()).toBeUndefined();
  });

  it("nests: the innermost run id wins, the outer is restored on exit", () => {
    run("outer", () => {
      expect(activeRunId()).toBe("outer");
      run("inner", () => {
        expect(activeRunId()).toBe("inner");
      });
      expect(activeRunId()).toBe("outer");
    });
  });

  it("exposes the same API on the track façade (Python parity)", () => {
    expect(track.run).toBe(run);
    expect(track.activeRunId).toBe(activeRunId);
  });
});

describe("agent name on the run scope", () => {
  // Cost grouped by agent was the least useful possible rollup — everything landed
  // under `unknown` — because nothing carried an agent name. `run()` is the only
  // place that knows which agent the work belongs to.
  it("exposes the agent name inside the run and nothing outside it", () => {
    expect(activeAgentName()).toBeUndefined();
    run("r1", { agentName: "build-alt" }, () => {
      expect(activeAgentName()).toBe("build-alt");
      expect(activeRunId()).toBe("r1");
    });
    expect(activeAgentName()).toBeUndefined();
  });

  it("keeps the two-argument form working (agent name is optional)", () => {
    run("r2", () => {
      expect(activeRunId()).toBe("r2");
      expect(activeAgentName()).toBeUndefined();
    });
  });
});

describe("the run store survives dual ESM/CJS loading", () => {
  // This package ships both formats. A host that mixes `import` and `require` — or
  // whose lockfile resolves two copies — loads BOTH builds, and a module-local
  // AsyncLocalStorage then means `run()` writes to one store while `activeRunId()`
  // reads another. The run id vanishes silently: cost captures fine, every outcome
  // lands unbound, and cost-per-outcome divides by zero with no error anywhere.
  it("holds the store on a process-global symbol, not in module scope", () => {
    const store = (globalThis as Record<symbol, unknown>)[Symbol.for("valuemaxx.runStore")];
    expect(store).toBeDefined();
  });

  it("a second copy of the module would read the same ambient run", () => {
    run("shared-scope", () => {
      // Whatever holds the global symbol is what any copy resolves to.
      const store = (globalThis as Record<symbol, unknown>)[Symbol.for("valuemaxx.runStore")];
      expect(store).toBeDefined();
      expect(activeRunId()).toBe("shared-scope");
    });
  });
});
