/**
 * T3 run_id injection (TS) — stamp the active run_id into an outbound SDK call's args.
 *
 * The TypeScript mirror of Python `valuemaxx.outcomes.instrument.injection`. At init() each
 * declared echoing call is wrapped: inside an active {@link run}, the run_id is
 * copy-on-write merged into the configured dotted `injectInto` path of the call's
 * first-argument options object, so the external system echoes it back on its later webhook
 * (an exact T3 join).
 *
 * Invariants (identical to the Python injector):
 *  - **Copy-on-write.** Only the dict spine along `injectInto` is cloned; the caller's own
 *    objects are never mutated (a later read of the caller's `metadata` must not see run_id).
 *  - **Fail-open by omission.** No active run → the call passes through untouched.
 *  - **Reported, never silent.** A target whose `method` is not a function is recorded in
 *    {@link InjectionReport.unresolved}, never a silent no-op (the H10 init-ordering rule).
 *  - **Never swallows a host error** — the wrapped call's throw propagates unchanged.
 *
 * TypeScript has no `importlib`, so a target names the owner OBJECT + method directly (the
 * host already holds its client instances, exactly as {@link instrumentMethod} does) rather
 * than a dotted module string. `injectInto` remains a dotted PATH within the options object.
 */

import { activeRunId } from "./run.js";

/** One declared injection target: the owner object, the method to wrap, and the inject path. */
export interface InjectionTarget {
  /** The object owning the method (e.g. `stripe.paymentIntents`). */
  readonly owner: Record<string, unknown>;
  /** The method name to wrap (e.g. `"create"`). */
  readonly method: string;
  /** The dotted passthrough path to merge run_id into (e.g. `"metadata.atm_run_id"`). */
  readonly injectInto: string;
}

/** The result of installing injection: which targets resolved, which did not. */
export interface InjectionReport {
  /** `owner.method` labels for every wrapped target. */
  readonly installed: readonly string[];
  /** `owner.method` labels for targets whose method was not a function at init. */
  readonly unresolved: readonly string[];
}

/** A best-effort label for a target, for the report (constructor name + method). */
function label(target: InjectionTarget): string {
  const ownerName = target.owner.constructor?.name ?? "object";
  return `${ownerName}.${target.method}`;
}

/**
 * Wrap each declared target's method to inject the active run_id; report what resolved.
 *
 * A target whose `method` is not a function is returned in {@link InjectionReport.unresolved}
 * and never wrapped — the caller surfaces it as a startup warning.
 */
export function installRunIdInjection(targets: readonly InjectionTarget[]): InjectionReport {
  const installed: string[] = [];
  const unresolved: string[] = [];
  for (const target of targets) {
    const original = target.owner[target.method];
    if (typeof original !== "function") {
      unresolved.push(label(target));
      continue;
    }
    const originalFn = original as (...args: unknown[]) => unknown;
    const path = target.injectInto.split(".");
    target.owner[target.method] = function (this: unknown, ...args: unknown[]): unknown {
      const runId = activeRunId();
      if (runId === undefined) {
        return originalFn.apply(this, args); // no active run → pass through untouched.
      }
      const merged = mergePath(args[0], path, runId);
      return originalFn.apply(this, [merged, ...args.slice(1)]);
    };
    installed.push(label(target));
  }
  return { installed, unresolved };
}

/**
 * Return a copy of `options` with `runId` set at `path` (copy-on-write spine).
 *
 * Only the object nodes along `path` are cloned; sibling values are shared by reference but
 * the caller's path objects are never mutated. A non-object `options` (or a missing node)
 * becomes a fresh object so the path is always creatable.
 */
function mergePath(options: unknown, path: readonly string[], runId: string): unknown {
  if (path.length === 0) {
    return options;
  }
  const root = shallowCopyNode(options);
  let cursor = root;
  for (let i = 0; i < path.length - 1; i += 1) {
    const segment = path[i]!;
    const child = shallowCopyNode(cursor[segment]);
    cursor[segment] = child;
    cursor = child;
  }
  cursor[path[path.length - 1]!] = runId;
  return root;
}

/** Copy a path node into a fresh object (or a new empty one if it isn't a plain object). */
function shallowCopyNode(node: unknown): Record<string, unknown> {
  if (typeof node === "object" && node !== null && !Array.isArray(node)) {
    return { ...(node as Record<string, unknown>) };
  }
  return {};
}
