/**
 * run() — ambient run_id binding via AsyncLocalStorage (H2).
 *
 * Mirrors the Python `sdks/python/tests/test_track.py`: the run id binds for the
 * duration of the call (including across awaited async work), restores the prior
 * value on exit (even on throw), and nests correctly without leaking.
 */

import { describe, expect, it } from "vitest";

import { activeRunId, run, track } from "../src/run.js";

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
