/**
 * TokenVector invariants (§5.2) — mirrors packages/core tokens.py.
 */

import { describe, expect, it } from "vitest";

import {
  TokenInvariantError,
  tokenVector,
  tokenVectorFromProvider,
  totalInput,
} from "../src/tokens.js";

describe("tokenVector", () => {
  it("rejects negative counts", () => {
    expect(() =>
      tokenVector({
        inputUncached: -1,
        cacheRead: 0,
        cacheWrite5m: 0,
        cacheWrite1h: 0,
        output: 0,
        reasoning: 0,
      }),
    ).toThrowError(TokenInvariantError);
  });

  it("enforces reasoning <= output (reasoning embedded within output)", () => {
    expect(() =>
      tokenVector({
        inputUncached: 0,
        cacheRead: 0,
        cacheWrite5m: 0,
        cacheWrite1h: 0,
        output: 2,
        reasoning: 5,
      }),
    ).toThrowError(/reasoning/);
  });

  it("sums the four input-side classes for totalInput", () => {
    const v = tokenVector({
      inputUncached: 10,
      cacheRead: 5,
      cacheWrite5m: 3,
      cacheWrite1h: 2,
      output: 7,
      reasoning: 1,
    });
    expect(totalInput(v)).toBe(20); // 10 + 5 + 3 + 2 (output/reasoning excluded)
  });
});

describe("tokenVectorFromProvider", () => {
  it("derives inputUncached as the remainder after cache classes", () => {
    const v = tokenVectorFromProvider({
      totalInput: 100,
      cacheRead: 40,
      cacheWrite5m: 10,
      cacheWrite1h: 0,
      output: 25,
      reasoning: 0,
    });
    expect(v.inputUncached).toBe(50); // 100 - (40 + 10 + 0)
  });

  it("rejects a usage object where cache tokens exceed total_input", () => {
    expect(() =>
      tokenVectorFromProvider({
        totalInput: 10,
        cacheRead: 20,
        cacheWrite5m: 0,
        cacheWrite1h: 0,
        output: 0,
        reasoning: 0,
      }),
    ).toThrowError(/exceed total_input/);
  });
});
