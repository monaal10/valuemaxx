/**
 * The valuemaxx capture gateway.
 *
 * An observe-only reverse proxy in front of the LLM providers. A host swaps its
 * `baseURL` and sets a couple of headers; the gateway forwards the request byte for
 * byte, watches the response go past, and reports cost to the backend out of band.
 *
 * Three invariants, in priority order:
 *
 *  1. **Never break the caller.** Any failure in our own logic falls back to a plain
 *     `fetch` passthrough with capture disabled. Losing a span is acceptable; losing
 *     a customer's request is not. This is why every capture step is wrapped.
 *  2. **Never change the request.** `x-vmx-*` headers are stripped; everything else
 *     — including the caller's provider key, which we do not store — is forwarded
 *     verbatim. The provider must see exactly what the host wrote.
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
import {
  H_RUN_ID_ECHO,
  forwardableHeaders,
  readIntent,
  type CaptureIntent,
} from "./headers.js";
import { reportOutcome, reportSpan } from "./report.js";

export interface Env {
  /** Backend base URL, e.g. https://api.valuemaxx.dev */
  readonly VALUEMAXX_BACKEND: string;
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
      return forwardOutcome(request, env);
    }

    const route = ROUTES.find(
      (r) => url.pathname === r.prefix || url.pathname.startsWith(`${r.prefix}/`),
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

    try {
      return await proxy(request, upstreamUrl, route.provider, env, ctx);
    } catch {
      // Invariant 1. Our bug must not become the caller's outage: retry the request
      // as a bare passthrough with no capture at all.
      return fetch(
        new Request(upstreamUrl, {
          method: request.method,
          headers: forwardableHeaders(request.headers),
          body: request.body,
        }),
      );
    }
  },
} satisfies ExportedHandler<Env>;

async function forwardOutcome(
  request: Request,
  env: Env,
): Promise<Response> {
  const key = request.headers.get("x-vmx-key")?.trim();
  if (!key) {
    return json({ error: "missing_key", message: "x-vmx-key is required" }, 401);
  }
  const body = await request.text();
  const upstream = await fetch(
    `${env.VALUEMAXX_BACKEND.replace(/\/+$/, "")}/outcome`,
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
  const intent = readIntent(request.headers, () => crypto.randomUUID());

  // The request body is needed twice: forwarded upstream, and read for the model
  // name (the response does not always carry it, e.g. Anthropic streaming). Buffer
  // it — LLM request bodies are prompts, not uploads.
  const requestBody =
    request.method === "GET" || request.method === "HEAD"
      ? undefined
      : await request.text();
  const requestedModel = readModel(requestBody);

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
  if (!intent.runIdWasMinted) return response;
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
}): Promise<void> {
  const { stream, isStream, provider, model, includeUsage, intent, env, status } =
    args;
  try {
    const observation = isStream
      ? await readStreaming(stream, provider, model, includeUsage)
      : await readNonStreaming(stream, provider, model);

    if (observation) {
      await reportSpan(env.VALUEMAXX_BACKEND, intent, observation.observation, {
        ...(observation.inlineCostUsd === undefined
          ? {}
          : { inlineCostUsd: observation.inlineCostUsd }),
      });
    }

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

