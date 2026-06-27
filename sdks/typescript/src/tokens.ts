/**
 * The token vector — usage split by class, with the enforced invariants (§5.2).
 *
 * Blending the input classes mis-prices the cached slice badly, so the vector is
 * *always* split by class: `inputUncached / cacheRead / cacheWrite5m /
 * cacheWrite1h / output / reasoning`. The 5m and 1h cache writes are DISTINCT
 * fields (never one flat `cacheWrite`). `reasoning` is DERIVED and embedded
 * within `output` (count of `type:"thinking"` blocks), never a separate input.
 *
 * Mirrors `packages/core/src/valuemaxx/core/tokens.py`. The same invariants are
 * enforced: all counts non-negative, `output >= reasoning`, and (in
 * {@link tokenVectorFromProvider}) cache tokens never exceed `total_input`.
 */

/** Per-attempt token usage, split by the six classes (§5.2). */
export interface TokenVector {
  readonly inputUncached: number;
  readonly cacheRead: number;
  readonly cacheWrite5m: number;
  readonly cacheWrite1h: number;
  readonly output: number;
  readonly reasoning: number;
}

/** Thrown when a token vector violates one of the enforced shape invariants. */
export class TokenInvariantError extends Error {
  public override readonly name = "TokenInvariantError";
}

function assertNonNegative(name: string, value: number): void {
  if (!Number.isInteger(value) || value < 0) {
    throw new TokenInvariantError(`${name} must be a non-negative integer, got ${value}`);
  }
}

/**
 * Construct a {@link TokenVector}, enforcing the always-on invariants (1)/(2)/(6):
 * all counts non-negative and `output >= reasoning` (reasoning lives inside output).
 */
export function tokenVector(v: TokenVector): TokenVector {
  assertNonNegative("inputUncached", v.inputUncached);
  assertNonNegative("cacheRead", v.cacheRead);
  assertNonNegative("cacheWrite5m", v.cacheWrite5m);
  assertNonNegative("cacheWrite1h", v.cacheWrite1h);
  assertNonNegative("output", v.output);
  assertNonNegative("reasoning", v.reasoning);
  if (v.reasoning > v.output) {
    throw new TokenInvariantError(
      `reasoning (${v.reasoning}) must not exceed output (${v.output}); ` +
        "reasoning is derived and embedded within output (§5.2)",
    );
  }
  return Object.freeze({
    inputUncached: v.inputUncached,
    cacheRead: v.cacheRead,
    cacheWrite5m: v.cacheWrite5m,
    cacheWrite1h: v.cacheWrite1h,
    output: v.output,
    reasoning: v.reasoning,
  });
}

/** Sum of the four input-side classes (output/reasoning are not input). */
export function totalInput(v: TokenVector): number {
  return v.inputUncached + v.cacheRead + v.cacheWrite5m + v.cacheWrite1h;
}

/**
 * Build a vector from a raw provider usage object, applying the cache guard.
 *
 * Providers report a single `totalInput` count plus the cache-token subsets;
 * `inputUncached` is *derived* as the remainder. Invariant (3)/(5): the cache
 * tokens can never exceed `totalInput` on a real response — a violation means
 * the usage object was mis-parsed, so we reject rather than silently mis-price
 * (which would otherwise surface as a negative uncached remainder).
 */
export function tokenVectorFromProvider(args: {
  totalInput: number;
  cacheRead: number;
  cacheWrite5m: number;
  cacheWrite1h: number;
  output: number;
  reasoning: number;
}): TokenVector {
  const cacheTotal = args.cacheRead + args.cacheWrite5m + args.cacheWrite1h;
  if (cacheTotal > args.totalInput) {
    throw new TokenInvariantError(
      `cache tokens (${cacheTotal}) exceed total_input (${args.totalInput}); ` +
        "provider usage object is inconsistent (§5.2 invariant 3)",
    );
  }
  return tokenVector({
    inputUncached: args.totalInput - cacheTotal,
    cacheRead: args.cacheRead,
    cacheWrite5m: args.cacheWrite5m,
    cacheWrite1h: args.cacheWrite1h,
    output: args.output,
    reasoning: args.reasoning,
  });
}
