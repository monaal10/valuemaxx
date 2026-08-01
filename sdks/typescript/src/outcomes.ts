/**
 * Declarative outcome instrumentation — the runtime half of `outcomes.yaml`.
 *
 * `valuemaxx onboard` has always RENDERED an `outcomes.yaml`, but nothing ever read
 * one: neither SDK loaded it, so a declared outcome fired nothing and
 * cost-per-outcome stayed unreachable no matter what the file said. This closes that
 * loop — the host declares what a business outcome IS, and calling the named function
 * records it, bound to whatever run is ambient at that moment.
 *
 * The contract is deliberately narrow:
 *
 * - A rule names a FUNCTION on an object the host hands us (`targets`). We wrap that
 *   property; every call fires the outcome after the function returns. We never
 *   monkey-patch a module registry or a global — an SDK that reaches into arbitrary
 *   module scope to find `markAltCreated` is impossible to reason about and worse to
 *   debug.
 * - The outcome fires only on SUCCESS. A throwing call is not an outcome; recording
 *   one would inflate the denominator with work that failed.
 * - Recording is FAIL-OPEN and off the host's return path: a POST failure is logged
 *   and swallowed. Cost instrumentation must never turn a working feature into a
 *   broken one.
 * - `signal_class` comes from the RULE, not the call site, and the binding tier is
 *   decided by the backend cascade. The host declares what happened; the system
 *   decides how much to trust the link.
 */

import { activeEntityKeys, activeRunId } from "./run.js";

/** One declarative rule, as rendered into `outcomes.yaml` by `valuemaxx onboard`. */
export interface OutcomeRule {
  /** The outcome's business name — what a rollup groups by (`alt_created`). */
  readonly name: string;
  /** The function whose successful call means this outcome happened. */
  readonly match_target: string;
  /** System-mapped signal class; defaults to a confirmed outcome. */
  readonly signal?: string | undefined;
}

/**
 * What a DIRECT caller states: just the outcome's name (and optionally its signal).
 *
 * Deliberately not `OutcomeRule` — `match_target` names the function whose call means
 * the outcome happened, and a direct caller IS that call site, so demanding one would
 * be asking it to describe itself.
 */
export interface DirectOutcome {
  /** The outcome's business name — what a rollup groups by (`alt_created`). */
  readonly name: string;
  /** System-mapped signal class; defaults to a confirmed outcome. */
  readonly signal?: string | undefined;
}

/** Provenance marker for an outcome recorded by an explicit call, not a wrapped fn. */
const DIRECT_MATCH_TARGET = "<direct>";

/** The parsed `outcomes.yaml` document. */
export interface OutcomesDocument {
  readonly outcomes?: readonly OutcomeRule[] | undefined;
}

/** What `installOutcomes` needs to record an outcome against the backend. */
export interface OutcomeRecorderConfig {
  readonly tenantId: string;
  readonly ingestKey: string;
  /** Base endpoint (the same one `init()` takes); `/bind_outcome` is appended. */
  readonly endpoint: string;
  readonly logger?: Pick<Console, "warn" | "error"> | undefined;
  /** Injectable for tests; defaults to global fetch. */
  readonly fetchImpl?: typeof fetch | undefined;
  /** Injectable id generator (tests pass a counter). */
  readonly newId?: (() => string) | undefined;
  /** Injectable clock (tests pass a fixed time). */
  readonly now?: (() => Date) | undefined;
}

/** An object owning functions a rule may name, e.g. `{ markAltCreated }`. */
export type OutcomeTargets = Record<string, unknown>;

/** A reversible wrap, so a host can uninstall instrumentation in tests. */
export interface OutcomeHandle {
  readonly outcomeName: string;
  readonly target: string;
  readonly restore: () => void;
}

/** The result of installing: what was wired, and what could not be. */
export interface InstallOutcomesResult {
  readonly handles: readonly OutcomeHandle[];
  /** Rules whose function was absent or not callable — reported, never silent. */
  readonly unresolved: readonly string[];
}

/** The trailing symbol of a `match_target` (`src/alts.ts:markAltCreated` -> the name). */
function targetFunctionName(matchTarget: string): string {
  const afterColon = matchTarget.includes(":")
    ? matchTarget.slice(matchTarget.lastIndexOf(":") + 1)
    : matchTarget;
  return afterColon.trim();
}

function defaultNewId(): string {
  // A uuid-shaped id; the backend brands it with the `oe_` prefix convention.
  const hex = (n: number): string =>
    Array.from({ length: n }, () => Math.floor(Math.random() * 16).toString(16)).join("");
  return `oe_${hex(8)}-${hex(4)}-4${hex(3)}-8${hex(3)}-${hex(12)}`;
}

/**
 * POST one outcome to the backend's `bind_outcome`.
 *
 * Fire-and-forget by design: the caller does not await this on its return path, and a
 * failure is logged rather than thrown. The run id is read from the ambient scope at
 * call time — that is what earns the `exact` binding tier when the host wrapped its
 * work in `run()`.
 */
async function recordOutcome(rule: OutcomeRule, config: OutcomeRecorderConfig): Promise<void> {
  const doFetch = config.fetchImpl ?? globalThis.fetch;
  const newId = config.newId ?? defaultNewId;
  const now = config.now ?? ((): Date => new Date());
  const runId = activeRunId();
  const base = config.endpoint.replace(/\/+$/, "");

  const body = {
    tenant_id: config.tenantId,
    id: newId(),
    name: rule.name,
    signal_class: rule.signal ?? "outcome_confirmed",
    value: null,
    occurred_at: now().toISOString(),
    // The tier is left null on purpose: the backend cascade decides it and
    // revalidates the run id. A caller cannot promote its own outcome to `exact`.
    binding: { run_id: runId ?? null, tier: null, bound_by: null },
    // Read from the ambient run scope, NOT invented here. These are what let one
    // unit span several runs ("cost per candidate" across build + screen), and they
    // cannot be backfilled — an outcome recorded without them stays unattributable.
    entity_keys: Object.entries(activeEntityKeys() ?? {}) as ReadonlyArray<
      readonly [string, string]
    >,
    correlation_id: null,
    source: "valuemaxx-sdk",
    raw: {},
  };

  const res = await doFetch(`${base}/bind_outcome`, {
    method: "POST",
    headers: { "content-type": "application/json", "x-api-key": config.ingestKey },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`bind_outcome responded ${res.status}`);
  }
}

/**
 * Record one outcome NOW, bound to whatever run is ambient at this moment.
 *
 * `installOutcomes` covers the case where "done" is a named function on an object we
 * can wrap. Plenty of hosts have no such function: a workflow step reaches its
 * terminal state as a RETURN VALUE inside a closure, a queue consumer acks a message,
 * a chat turn resolves a completion. Those call sites own nothing patchable, so
 * without a direct call they could bind runs perfectly and still never record the
 * outcome those runs exist to explain — leaving cost-per-outcome null forever.
 *
 * Same honesty contract as the declarative path: the tier is left null for the
 * backend cascade to decide, the entity keys come from the ambient run scope rather
 * than the call site, and the caller cannot promote its own outcome to `exact`.
 *
 * Unlike the wrapped path this DOES reject on a failed POST, because a direct caller
 * has a `try`/`catch` and can decide. Wrap it in one — recording an outcome must
 * never turn a working feature into a broken one.
 */
export async function recordOutcomeNow(
  outcome: DirectOutcome,
  config: OutcomeRecorderConfig,
): Promise<void> {
  await recordOutcome({ ...outcome, match_target: DIRECT_MATCH_TARGET }, config);
}

/**
 * Wrap every rule's named function on `targets` so a successful call records the outcome.
 *
 * Returns reversible handles plus the rules it could NOT resolve — an unresolved rule
 * is reported rather than silently ignored, because a declared outcome that never
 * fires looks identical to an outcome that never happened.
 */
export function installOutcomes(
  document: OutcomesDocument,
  targets: OutcomeTargets,
  config: OutcomeRecorderConfig,
): InstallOutcomesResult {
  const logger = config.logger ?? console;
  const handles: OutcomeHandle[] = [];
  const unresolved: string[] = [];

  for (const rule of document.outcomes ?? []) {
    const fnName = targetFunctionName(rule.match_target);
    const original = targets[fnName];
    if (typeof original !== "function") {
      unresolved.push(`${rule.name} -> ${fnName}`);
      continue;
    }

    const wrapped = function (this: unknown, ...args: unknown[]): unknown {
      const result = (original as (...a: unknown[]) => unknown).apply(this, args);
      // Only a SUCCESSFUL call is an outcome. For a promise that means waiting for it
      // to resolve — a rejected promise records nothing.
      if (result instanceof Promise) {
        return result.then((value: unknown) => {
          void recordOutcome(rule, config).catch((err: unknown) => {
            logger.warn(`valuemaxx: failed to record outcome ${rule.name}: ${String(err)}`);
          });
          return value;
        });
      }
      void recordOutcome(rule, config).catch((err: unknown) => {
        logger.warn(`valuemaxx: failed to record outcome ${rule.name}: ${String(err)}`);
      });
      return result;
    };

    targets[fnName] = wrapped;
    handles.push({
      outcomeName: rule.name,
      target: fnName,
      restore: () => {
        targets[fnName] = original;
      },
    });
  }

  if (unresolved.length > 0) {
    logger.warn(
      `valuemaxx: ${unresolved.length} declared outcome(s) matched no function and will ` +
        `never fire: ${unresolved.join(", ")}`,
    );
  }
  return { handles, unresolved };
}
