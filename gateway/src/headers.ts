/**
 * The gateway's request contract: what a caller may say with headers alone.
 *
 * This is the entire integration surface. A host swaps its `baseURL` and sets these
 * on the client it already has — no SDK, no run boundary, no flush. Everything the
 * old SDK asked for in code is expressible here as a string:
 *
 * - `x-vmx-key`        which tenant this is (resolved server-side; never trusted from a body)
 * - `x-vmx-run-id`     what unit of work this call belongs to
 * - `x-vmx-agent`      which agent to group it under
 * - `x-vmx-entity-*`   durable business ids the unit is about
 * - `x-vmx-outcome`    the business outcome this call completes
 * - `x-vmx-call-site`  a confirmed call site eligible for bounded deployment
 * - `x-vmx-bypass`     the immediate original-config escape hatch
 * - `x-vmx-experiment` / `x-vmx-variant` / `x-vmx-app`  which arm of which comparison
 *   this call belongs to. No engine reads them yet; they are captured now because a
 *   variant stamp cannot be added to traffic after the fact.
 *
 * Every `x-vmx-*` header is STRIPPED before the request is forwarded upstream: the
 * provider never sees gateway control metadata. Request-body deployment is handled
 * separately and remains disabled by default.
 */

/** Header names, lowercased — Workers' `Headers` is case-insensitive but iteration is not. */
export const VMX_PREFIX = "x-vmx-";
export const H_KEY = "x-vmx-key";
export const H_RUN_ID = "x-vmx-run-id";
export const H_AGENT = "x-vmx-agent";
export const H_OUTCOME = "x-vmx-outcome";
export const H_ENTITY_PREFIX = "x-vmx-entity-";
export const H_EXPERIMENT = "x-vmx-experiment";
export const H_VARIANT = "x-vmx-variant";
/** The arms of the experiment, comma-separated — what the gateway assigns FROM. */
export const H_VARIANTS = "x-vmx-variants";
export const H_APP = "x-vmx-app";
/** Stable confirmed call-site identity; required before a deployment can apply. */
export const H_CALL_SITE = "x-vmx-call-site";
/** One-line host escape hatch: truthy means serve the host's original body. */
export const H_BYPASS = "x-vmx-bypass";
/** W3C baggage — the standard alias for `x-vmx-run-id`, so existing tracing works. */
export const H_BAGGAGE = "baggage";
/** The run id is echoed back so a host can stamp it into an external system later. */
export const H_RUN_ID_ECHO = "x-vmx-run-id";

/** The W3C baggage key the backend's T2 resolver reads. Must match `core.wire`. */
export const BAGGAGE_RUN_ID_KEY = "valuemaxx.run_id";

export interface CaptureIntent {
  /** Tenant key. Absent means capture is skipped entirely (the request still flows). */
  readonly key: string | undefined;
  /** The unit of work. Caller-supplied, else minted. */
  readonly runId: string;
  /** True when the gateway minted the run id (so we echo it back). */
  readonly runIdWasMinted: boolean;
  readonly agentName: string | undefined;
  /** `x-vmx-entity-foo-bar: 1` → `{ foo_bar: "1" }` — hyphens map to underscores. */
  readonly entityKeys: Readonly<Record<string, string>>;
  readonly outcome: string | undefined;
  /** Which comparison this call is an arm of. Recorded, not yet acted on. */
  readonly experiment: string | undefined;
  readonly variant: string | undefined;
  /**
   * The arms the host declared for this experiment.
   *
   * The host names them rather than the gateway holding a registry, because there is
   * no per-tenant config store yet and inventing one to hold two strings would be a
   * larger commitment than the feature warrants. It also keeps the invariant that a
   * request says everything about itself.
   */
  readonly variants: readonly string[];
  /** Which of the host's apps/surfaces made the call — one tenant, several products. */
  readonly app: string | undefined;
  readonly callSiteId: string | undefined;
  readonly bypassOptimization: boolean;
}

/**
 * Read the capture intent from a request's headers.
 *
 * Never throws: a malformed value degrades that one field rather than the request.
 * Capture is best-effort by construction — the caller's LLM call is not.
 */
export function readIntent(
  headers: Headers,
  mintId: () => string,
): CaptureIntent {
  const explicitRunId = headers.get(H_RUN_ID)?.trim();
  const baggageRunId = explicitRunId
    ? undefined
    : parseBaggageRunId(headers.get(H_BAGGAGE));
  const carried = explicitRunId || baggageRunId;

  const entityKeys: Record<string, string> = {};
  for (const [name, value] of headers) {
    const lower = name.toLowerCase();
    if (!lower.startsWith(H_ENTITY_PREFIX) || !value) continue;
    const key = lower.slice(H_ENTITY_PREFIX.length).replaceAll("-", "_");
    if (key) entityKeys[key] = value;
  }

  return {
    key: headers.get(H_KEY)?.trim() || undefined,
    runId: carried || mintId(),
    runIdWasMinted: !carried,
    agentName: headers.get(H_AGENT)?.trim() || undefined,
    entityKeys,
    outcome: headers.get(H_OUTCOME)?.trim() || undefined,
    experiment: headers.get(H_EXPERIMENT)?.trim() || undefined,
    variant: headers.get(H_VARIANT)?.trim() || undefined,
    variants: parseVariants(headers.get(H_VARIANTS)),
    app: headers.get(H_APP)?.trim() || undefined,
    callSiteId: headers.get(H_CALL_SITE)?.trim() || undefined,
    bypassOptimization: isTruthy(headers.get(H_BYPASS)),
  };
}

function isTruthy(raw: string | null): boolean {
  return raw === "1" || raw?.toLowerCase() === "true" || raw?.toLowerCase() === "on";
}

/**
 * The declared arms, trimmed and de-blanked.
 *
 * A malformed list degrades to no arms — and therefore to no assignment — rather
 * than producing an arm named "" or a one-armed comparison, either of which would
 * record traffic as belonging to an experiment that cannot be analysed.
 */
function parseVariants(raw: string | null): readonly string[] {
  if (!raw) return [];
  return raw
    .split(",")
    .map((v) => v.trim())
    .filter((v) => v.length > 0);
}

/** Extract the run id from a W3C `baggage` header, or undefined. */
function parseBaggageRunId(raw: string | null): string | undefined {
  if (!raw) return undefined;
  for (const member of raw.split(",")) {
    const eq = member.indexOf("=");
    if (eq < 0) continue;
    const key = member.slice(0, eq).trim();
    if (key !== BAGGAGE_RUN_ID_KEY) continue;
    // Strip any `;`-suffixed baggage properties — the value ends at the first one.
    const value = member
      .slice(eq + 1)
      .split(";")[0]
      ?.trim();
    if (value) return decodeURIComponent(value);
  }
  return undefined;
}

/**
 * The headers to forward upstream: everything the host sent MINUS our own.
 *
 * `host` goes too — it names the gateway, and forwarding it would make the provider
 * reject the request (or worse, route it somewhere unintended).
 */
export function forwardableHeaders(headers: Headers): Headers {
  const out = new Headers();
  for (const [name, value] of headers) {
    const lower = name.toLowerCase();
    if (lower.startsWith(VMX_PREFIX)) continue;
    if (lower === "host" || lower === "content-length") continue;
    // `accept-encoding` is dropped so the provider replies uncompressed. The gateway
    // must READ the response to count tokens, and it re-emits the body under the
    // provider's original `content-encoding` header — forwarding this would promise
    // the client an encoding the tee'd branch has already decoded away.
    if (lower === "accept-encoding") continue;
    out.set(name, value);
  }
  return out;
}

/**
 * Deterministically assign a unit of work to an experiment arm.
 *
 * Assignment must be a pure function of (run id, experiment) rather than random,
 * because a unit is many calls: a run that draws arm A on its first call and arm B
 * on its second has been served by both models, so its outcome belongs to neither
 * and the experiment measures a blend instead of a comparison. Hashing gives that
 * stability with no state to store and no coordination between isolates.
 *
 * The experiment name is folded into the hash so two experiments do not correlate.
 * Sharing one hash would put the same runs in the "first" arm of every experiment,
 * silently inheriting each experiment's selection effects into the next.
 *
 * Returns undefined when there is nothing to assign, so a caller can always call it
 * and let the absence of an experiment mean "no variant" rather than branch first.
 */
export async function assignVariant(
  runId: string,
  experiment: string,
  variants: readonly string[],
): Promise<string | undefined> {
  if (!experiment || variants.length === 0) return undefined;
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(`${experiment}:${runId}`),
  );
  // The first four bytes are ample: 2^32 buckets over a handful of arms, and the
  // modulo bias at that ratio is far below the noise any experiment tolerates.
  const view = new DataView(digest);
  return variants[view.getUint32(0) % variants.length];
}

/**
 * Fill in the experiment arm the gateway is responsible for choosing.
 *
 * Three rules, in priority order, each protecting a different thing:
 *
 * 1. **A host-supplied variant always wins.** A host running its own assignment — a
 *    feature flag, a staged rollout — is the authority on which arm served this call.
 *    Relabelling it would make the recorded arm disagree with the model that actually
 *    ran, which is worse than not recording an arm at all.
 * 2. **No experiment means no arm.** Ordinary traffic passes through untouched;
 *    stamping it would enrol every unrelated call in a comparison nobody declared.
 * 3. **Otherwise the gateway assigns**, deterministically on the run id. This is the
 *    reason the function exists: a host choosing its own arms has no randomisation
 *    guarantee, and any correlation between that choice and traffic source, time of
 *    day or customer size gets measured as if it were the model's effect.
 *
 * Separate from `readIntent` because assignment needs Web Crypto and is therefore
 * async, while reading headers is not — keeping the split means the parse stays a
 * pure synchronous function.
 */
export async function withAssignedVariant(
  intent: CaptureIntent,
  variants: readonly string[],
): Promise<CaptureIntent> {
  if (intent.variant || !intent.experiment) return intent;
  const variant = await assignVariant(
    intent.runId,
    intent.experiment,
    variants,
  );
  return variant ? { ...intent, variant } : intent;
}

/**
 * Echo the assigned arm so the host can act on it.
 *
 * This is where an observe-only proxy meets its honest limit. By the time the gateway
 * sees a request the host has already chosen a model, and changing it would mean
 * rewriting the request — breaking the invariant the whole design rests on. So the
 * gateway cannot make THIS call use the assigned arm.
 *
 * What it can do is decide the arm and hand it back. The host reads the header once
 * per unit of work and uses it for that unit's calls. The assignment is still the
 * gateway's — deterministic, unbiased, not correlated with anything in the host's
 * traffic — while the choice of what to run stays the host's, which is the only place
 * it can safely live.
 */
export function withVariantEcho(
  response: Response,
  intent: CaptureIntent,
): Response {
  if (!intent.variant) return response;
  const headers = new Headers(response.headers);
  headers.set(H_VARIANT, intent.variant);
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}
