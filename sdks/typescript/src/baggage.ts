/**
 * T2 baggage producer (TS) — carry the active run_id across a live hop on W3C baggage.
 *
 * The TypeScript mirror of Python `valuemaxx.outcomes.instrument.baggage`. At init() each
 * declared outbound HTTP call is wrapped: inside an active {@link run}, the run_id is
 * copy-on-write merged as a `valuemaxx.run_id=<id>` member of the outbound `baggage` header,
 * so the receiving service parses it back and the cascade binds `exact` (T2).
 *
 * The baggage KEY is read from the shared wire contract (`run_id_wire.json`, generated from
 * the Python single source), so the TS producer and the backend cascade cannot drift.
 *
 * Invariants (identical to the T3 injector):
 *  - **Copy-on-write** on the caller's headers object.
 *  - **List-merge, not clobber**: existing baggage members survive; our key is replaced in
 *    place if already present (never a duplicate member), per the W3C list format.
 *  - **Pass-through** with no active run.
 *  - **Reported, never silent**: a target whose method is not a function is returned in
 *    `unresolved`.
 *  - **Never swallows a host error** — the wrapped call's throw propagates unchanged.
 */

import type { InjectionReport } from "./injection.js";
import { activeRunId } from "./run.js";
import wire from "./run_id_wire.json" with { type: "json" };

const BAGGAGE_RUN_ID_KEY = wire.baggage_run_id_key;
const HEADERS_KEY = "headers";
const BAGGAGE_HEADER = "baggage";

/** One declared HTTP target: the owner object and the method to wrap. */
export interface BaggageTarget {
  /** The object owning the method (e.g. an http client instance). */
  readonly owner: Record<string, unknown>;
  /** The method name to wrap (e.g. `"request"`). */
  readonly method: string;
}

function label(target: BaggageTarget): string {
  const ownerName = target.owner.constructor?.name ?? "object";
  return `${ownerName}.${target.method}`;
}

/**
 * Wrap each declared HTTP target's method to stamp the active run_id onto W3C baggage;
 * report what resolved. An unresolved target is returned in `unresolved`, never wrapped.
 */
export function installRunIdBaggage(targets: readonly BaggageTarget[]): InjectionReport {
  const installed: string[] = [];
  const unresolved: string[] = [];
  for (const target of targets) {
    const original = target.owner[target.method];
    if (typeof original !== "function") {
      unresolved.push(label(target));
      continue;
    }
    const originalFn = original as (...args: unknown[]) => unknown;
    target.owner[target.method] = function (this: unknown, ...args: unknown[]): unknown {
      const runId = activeRunId();
      if (runId === undefined) {
        return originalFn.apply(this, args); // no active run → pass through untouched.
      }
      const merged = mergeBaggage(args[0], runId);
      return originalFn.apply(this, [merged, ...args.slice(1)]);
    };
    installed.push(label(target));
  }
  return { installed, unresolved };
}

/**
 * Return a copy of `options` with run_id merged into its `headers.baggage` member.
 *
 * Copy-on-write: only the options object and its `headers` object are cloned; the caller's
 * own headers object is never mutated. Existing baggage members are preserved; our key is
 * replaced in place if already present.
 */
function mergeBaggage(options: unknown, runId: string): unknown {
  const root = shallowCopy(options);
  const headers = shallowCopy(root[HEADERS_KEY]);
  headers[BAGGAGE_HEADER] = withRunIdMember(headers[BAGGAGE_HEADER], runId);
  root[HEADERS_KEY] = headers;
  return root;
}

/** Copy a node into a fresh object (or a new empty one if it isn't a plain object). */
function shallowCopy(node: unknown): Record<string, unknown> {
  if (typeof node === "object" && node !== null && !Array.isArray(node)) {
    return { ...(node as Record<string, unknown>) };
  }
  return {};
}

/** Build the W3C baggage value: existing members (minus a stale run_id) + ours. */
function withRunIdMember(existing: unknown, runId: string): string {
  const members: string[] = [];
  if (typeof existing === "string" && existing.trim() !== "") {
    for (const raw of existing.split(",")) {
      const member = raw.trim();
      if (member !== "" && !member.startsWith(`${BAGGAGE_RUN_ID_KEY}=`)) {
        members.push(member);
      }
    }
  }
  members.push(`${BAGGAGE_RUN_ID_KEY}=${runId}`);
  return members.join(",");
}
