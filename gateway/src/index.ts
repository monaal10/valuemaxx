/**
 * The valuemaxx capture gateway.
 *
 * An observe-only-by-default reverse proxy in front of the LLM providers. A host swaps its
 * `baseURL` and sets a couple of headers; the gateway forwards the request byte for
 * byte, watches the response go past, and reports cost to the backend out of band.
 *
 * Three invariants, in priority order:
 *
 *  1. **Never break the caller.** Any failure in our own logic falls back to a plain
 *     `fetch` passthrough with capture disabled. Losing a span is acceptable; losing
 *     a customer's request is not. This is why every capture step is wrapped.
 *  2. **Never change the request by default.** `x-vmx-*` headers are stripped and
 *     everything else is forwarded verbatim. A bounded config change is possible
 *     only under an explicit, source-matched, call-site-scoped deployment policy.
 *  3. **Never delay the response.** The response body is `tee()`d: one branch streams
 *     to the client untouched and unbuffered, the other feeds the accumulator. Capture
 *     and reporting happen in `waitUntil`, after the client already has its bytes.
 */

import {
  foldSseChunk,
  newAccumulator,
  observeNonStreaming,
  readInlineCost,
  requestedStreamUsage,
  type Provider,
  type StreamAccumulator,
} from "./capture.js";
import { prepareRequestBody, type ConfigIdentity } from "./config.js";
import {
  H_RUN_ID_ECHO,
  forwardableHeaders,
  readIntent,
  withAssignedVariant,
  withVariantEcho,
  type CaptureIntent,
} from "./headers.js";
import { reportOutcome, reportSpan } from "./report.js";

export interface Env {
  /** Backend base URL, e.g. https://api.valuemaxx.dev */
  readonly VALUEMAXX_BACKEND: string;
  /** Observe-only unless explicitly set to `true` or `1`. */
  readonly VALUEMAXX_ENFORCEMENT_ENABLED?: string;
  /** A strictly validated, source-matched deployment snapshot. */
  readonly VALUEMAXX_DEPLOYMENT_POLICY?: string;
}

/** Where each route prefix forwards to, and how to read usage from it. */
const ROUTES: ReadonlyArray<{
  readonly prefix: string;
  readonly provider: Provider;
  readonly upstream: string;
}> = [
  { prefix: "/openai", provider: "openai", upstream: "https://api.openai.com" },
  {
    prefix: "/anthropic",
    provider: "anthropic",
    upstream: "https://api.anthropic.com",
  },
  {
    prefix: "/gemini",
    provider: "gemini",
    upstream: "https://generativelanguage.googleapis.com",
  },
  {
    prefix: "/openrouter",
    provider: "openrouter",
    upstream: "https://openrouter.ai/api",
  },
];

export default {
  async fetch(
    request: Request,
    env: Env,
    ctx: ExecutionContext,
  ): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === "/healthz") {
      return new Response("ok", { status: 200 });
    }

    // The outcome floor. Most outcomes ride the request that produced them via
    // `x-vmx-outcome`; a host whose "done" moment has no adjacent LLM call posts
    // here instead. Routed through the gateway so a host configures ONE base URL
    // rather than learning the backend's address separately.
    if (url.pathname === "/v1/outcome" && request.method === "POST") {
      return forwardOutcome(request, env, url.search);
    }

    const route = ROUTES.find(
      (r) =>
        url.pathname === r.prefix || url.pathname.startsWith(`${r.prefix}/`),
    );
    if (!route) {
      return json(
        {
          error: "unknown_route",
          message: `No provider route matches ${url.pathname}. Expected one of: ${ROUTES.map((r) => r.prefix).join(", ")}`,
        },
        404,
      );
    }

    const upstreamUrl = new URL(
      url.pathname.slice(route.prefix.length) + url.search,
      route.upstream,
    );

    // Clone before proxy() consumes the body. If our path throws afterwards, the
    // fallback still owns an untouched stream and can send the host's original bytes.
    const fallbackRequest = request.clone();
    try {
      return await proxy(request, upstreamUrl, route.provider, env, ctx);
    } catch {
      // Invariant 1. Our bug must not become the caller's outage: retry the request
      // as a bare passthrough with no capture at all.
      return fetch(
        new Request(upstreamUrl, {
          method: request.method,
          headers: forwardableHeaders(request.headers),
          body: fallbackRequest.body,
        }),
      );
    }
  },
} satisfies ExportedHandler<Env>;

async function forwardOutcome(
  request: Request,
  env: Env,
  search: string,
): Promise<Response> {
  const key = request.headers.get("x-vmx-key")?.trim();
  if (!key) {
    return json(
      { error: "missing_key", message: "x-vmx-key is required" },
      401,
    );
  }
  const body = await request.text();
  // The query string carries contract options (`?strict=true`); dropping it here
  // silently downgraded strict mode to permissive — found live, not in review.
  const upstream = await fetch(
    `${env.VALUEMAXX_BACKEND.replace(/\/+$/, "")}/outcome${search}`,
    {
      method: "POST",
      headers: { "content-type": "application/json", "x-api-key": key },
      body,
    },
  );
  return new Response(upstream.body, {
    status: upstream.status,
    headers: { "content-type": "application/json" },
  });
}

async function proxy(
  request: Request,
  upstreamUrl: URL,
  provider: Provider,
  env: Env,
  ctx: ExecutionContext,
): Promise<Response> {
  // Assignment happens before anything else so the arm is on the span whether the
  // call succeeds or not, and so a failed request still counts toward its arm — an
  // experiment that silently drops its failures compares two success-only worlds.
  const parsed = readIntent(request.headers, () => crypto.randomUUID());
  const intent = await withAssignedVariant(parsed, parsed.variants);

  // The request body is needed twice: forwarded upstream, and read for the model
  // name (the response does not always carry it, e.g. Anthropic streaming). Buffer
  // it — LLM request bodies are prompts, not uploads.
  const originalRequestBody =
    request.method === "GET" || request.method === "HEAD"
      ? undefined
      : await request.text();
  const prepared = await prepareRequestBody({
    provider,
    originalBody: originalRequestBody,
    runId: intent.runId,
    callSiteId: intent.callSiteId,
    bypass: intent.bypassOptimization,
    enforcementEnabled: enforcementEnabled(env.VALUEMAXX_ENFORCEMENT_ENABLED),
    policyRaw: env.VALUEMAXX_DEPLOYMENT_POLICY,
  });
  const requestBody = prepared.body;
  const requestedModel = readModel(requestBody);

  const startedAt = Date.now();
  const upstream = await fetch(
    new Request(upstreamUrl, {
      method: request.method,
      headers: forwardableHeaders(request.headers),
      ...(requestBody === undefined ? {} : { body: requestBody }),
    }),
  );

  // Capture is opt-in on the key. No key means the gateway is a plain proxy — which
  // is a legitimate way to try it before signing up.
  if (!intent.key || !upstream.body) {
    return withEcho(upstream, intent);
  }

  const [toClient, toCapture] = upstream.body.tee();
  const isStream = (upstream.headers.get("content-type") ?? "").includes(
    "text/event-stream",
  );

  ctx.waitUntil(
    capture({
      stream: toCapture,
      isStream,
      provider,
      model: requestedModel,
      includeUsage: requestedStreamUsage(requestBody),
      intent,
      env,
      status: upstream.status,
      startedAt,
      configIdentity: prepared.identity,
    }),
  );

  return withEcho(
    new Response(toClient, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: upstream.headers,
    }),
    intent,
  );
}

/** Echo the run id so a host can stamp it into an external system for later binding. */
function withEcho(response: Response, intent: CaptureIntent): Response {
  const withVariant = withVariantEcho(response, intent);
  if (!intent.runIdWasMinted) return withVariant;
  response = withVariant;
  const headers = new Headers(response.headers);
  headers.set(H_RUN_ID_ECHO, intent.runId);
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

async function capture(args: {
  stream: ReadableStream<Uint8Array>;
  isStream: boolean;
  provider: Provider;
  model: string;
  includeUsage: boolean;
  intent: CaptureIntent;
  env: Env;
  status: number;
  startedAt: number;
  configIdentity: ConfigIdentity | undefined;
}): Promise<void> {
  const {
    stream,
    isStream,
    provider,
    model,
    includeUsage,
    intent,
    env,
    status,
    startedAt,
    configIdentity,
  } = args;
  try {
    const observation = isStream
      ? await readStreaming(stream, provider, model, includeUsage)
      : await readNonStreaming(stream, provider, model);

    // Provider errors commonly omit usage. They must still become attempts or the
    // fast error-rate rollback signal sees only successful traffic. Zero tokens plus
    // `partialRecovered` says usage was unavailable; it does not invent billed use.
    const reported = observation?.observation ?? emptyObservation(provider, model, isStream);
    // Measured here rather than at the response, so a stream is timed to its LAST
    // byte. Timing a 30s generation to its headers would report ~200ms and make
    // every streaming model look equally fast.
    await reportSpan(env.VALUEMAXX_BACKEND, intent, reported, {
      ...(observation?.inlineCostUsd === undefined
        ? {}
        : { inlineCostUsd: observation.inlineCostUsd }),
      latencyMs: Date.now() - startedAt,
      status,
      ...(configIdentity === undefined ? {} : { configIdentity }),
    });

    // The outcome fires only on a successful call. A failed request is not an
    // outcome, and recording one would inflate the denominator with work that did
    // not happen — every unit would look cheaper than it is.
    if (intent.outcome && status >= 200 && status < 300) {
      await reportOutcome(env.VALUEMAXX_BACKEND, intent);
    }
  } catch {
    // Invariant 1 again: the client already has its bytes. A capture failure here is
    // a lost span, nothing more.
  }
}

interface CaptureResult {
  readonly observation: ReturnType<StreamAccumulator["finalizeObservation"]>;
  readonly inlineCostUsd?: number;
}

function emptyObservation(
  provider: Provider,
  model: string,
  isStreaming: boolean,
): ReturnType<StreamAccumulator["finalizeObservation"]> {
  return {
    provider,
    model,
    tokens: {
      inputUncached: 0,
      cacheRead: 0,
      cacheWrite5m: 0,
      cacheWrite1h: 0,
      output: 0,
      reasoning: 0,
    },
    isStreaming,
    partialRecovered: true,
  };
}

async function readStreaming(
  stream: ReadableStream<Uint8Array>,
  provider: Provider,
  model: string,
  includeUsage: boolean,
): Promise<CaptureResult | undefined> {
  const acc = newAccumulator(provider, { includeUsage });
  const reader = stream.pipeThrough(new TextDecoderStream()).getReader();
  let carry = "";
  let complete = false;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) {
        complete = true;
        break;
      }
      carry = foldSseChunk(acc, value, carry);
    }
  } finally {
    reader.releaseLock();
  }
  // A stream that ended early (client disconnect) still yields what we saw, flagged
  // partial — the alternative is silently under-reporting the spend to zero.
  if (!complete) acc.markCancelled();
  return { observation: acc.finalizeObservation({ provider, model }) };
}

async function readNonStreaming(
  stream: ReadableStream<Uint8Array>,
  provider: Provider,
  model: string,
): Promise<CaptureResult | undefined> {
  const text = await new Response(stream).text();
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return undefined;
  }
  if (!parsed || typeof parsed !== "object") return undefined;
  const body = parsed as Record<string, unknown>;
  const observation = observeNonStreaming(provider, body, model);
  if (!observation) return undefined;
  const inlineCostUsd =
    provider === "openrouter" ? readInlineCost(body) : undefined;
  return {
    observation,
    ...(inlineCostUsd === undefined ? {} : { inlineCostUsd }),
  };
}

/** The model the caller asked for — the response may omit it on streaming paths. */
function readModel(requestBody: string | undefined): string {
  if (!requestBody) return "";
  try {
    const parsed: unknown = JSON.parse(requestBody);
    if (parsed && typeof parsed === "object") {
      const model = (parsed as Record<string, unknown>)["model"];
      if (typeof model === "string") return model;
    }
  } catch {
    // Not JSON (or not a shape we know) — the response usually carries the model.
  }
  return "";
}

function json(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function enforcementEnabled(raw: string | undefined): boolean {
  return raw === "1" || raw?.toLowerCase() === "true";
}
