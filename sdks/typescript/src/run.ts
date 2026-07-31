/**
 * `track.run` — establish the ambient run_id for cost binding (§5.1, H2).
 *
 * The instrumentation reads the active run id off an `AsyncLocalStorage` store
 * (the Node equivalent of Python `contextvars`); {@link run} is the one-liner
 * the host wraps around an agent run so every LLM call inside binds to it. The
 * store automatically restores the prior value on exit (including on a thrown
 * error), so nesting and error paths never leak a stale run id.
 *
 * Mirrors the Python `valuemaxx.sdk.track.run`.
 */

import { AsyncLocalStorage } from "node:async_hooks";

interface RunContext {
  readonly runId: string;
  /** Which agent this run belongs to; stamped on every span so cost rolls up by agent. */
  readonly agentName?: string | undefined;
}

/**
 * The run store, held on a process-global symbol rather than in module scope.
 *
 * This package ships dual ESM+CJS, and a host that mixes `import` and `require` (or
 * resolves two copies through a lockfile) loads BOTH builds. A module-local
 * `AsyncLocalStorage` then means `run()` writes to one store while `activeRunId()`
 * reads another, so the run id silently vanishes: cost captures fine, every outcome
 * lands unbound, and cost-per-outcome divides by zero with no error anywhere. Sharing
 * one store across every copy in the process is what makes the binding survive.
 */
const STORE_KEY = Symbol.for("valuemaxx.runStore");

type GlobalWithStore = typeof globalThis & {
  [STORE_KEY]?: AsyncLocalStorage<RunContext>;
};

const globalRef = globalThis as GlobalWithStore;
const storage: AsyncLocalStorage<RunContext> =
  globalRef[STORE_KEY] ?? (globalRef[STORE_KEY] = new AsyncLocalStorage<RunContext>());

/** The active run id bound by an enclosing {@link run}, or `undefined` if none. */
export function activeRunId(): string | undefined {
  return storage.getStore()?.runId;
}

/** The active agent name bound by an enclosing {@link run}, or `undefined` if none. */
export function activeAgentName(): string | undefined {
  return storage.getStore()?.agentName;
}

/**
 * Run `fn` with `runId` bound as the ambient run for the duration of the call.
 *
 * Every LLM call captured inside `fn` (including in awaited async work that
 * inherits this async context) binds to `runId`. The previous ambient value is
 * restored automatically on return or throw — `AsyncLocalStorage.run` scopes
 * the store to exactly this call. Returns whatever `fn` returns.
 *
 * @example
 * await run("checkout-agent-42", async () => {
 *   await openai.chat.completions.create({ ... }); // binds to "checkout-agent-42"
 * });
 */
export function run<T>(runId: string, fn: () => T): T;
export function run<T>(runId: string, options: RunOptions, fn: () => T): T;
export function run<T>(
  runId: string,
  optionsOrFn: RunOptions | (() => T),
  maybeFn?: () => T,
): T {
  const fn = typeof optionsOrFn === "function" ? optionsOrFn : maybeFn;
  const options = typeof optionsOrFn === "function" ? undefined : optionsOrFn;
  if (fn === undefined) {
    throw new TypeError("run(runId, [options], fn): fn is required");
  }
  return storage.run({ runId, agentName: options?.agentName }, fn);
}

/** Optional per-run metadata. `agentName` is what cost-by-agent rollups group on. */
export interface RunOptions {
  readonly agentName?: string | undefined;
}

/** The run-context façade, mirroring Python's `valuemaxx.track`. */
export const track = {
  run,
  activeRunId,
  activeAgentName,
} as const;
