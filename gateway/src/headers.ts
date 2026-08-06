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
 *
 * Every `x-vmx-*` header is STRIPPED before the request is forwarded upstream: the
 * provider must see exactly the request the host wrote, or the gateway has changed
 * the semantics of the call it was only supposed to observe.
 */

/** Header names, lowercased — Workers' `Headers` is case-insensitive but iteration is not. */
export const VMX_PREFIX = "x-vmx-";
export const H_KEY = "x-vmx-key";
export const H_RUN_ID = "x-vmx-run-id";
export const H_AGENT = "x-vmx-agent";
export const H_OUTCOME = "x-vmx-outcome";
export const H_ENTITY_PREFIX = "x-vmx-entity-";
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
  };
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
    const value = member.slice(eq + 1).split(";")[0]?.trim();
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
