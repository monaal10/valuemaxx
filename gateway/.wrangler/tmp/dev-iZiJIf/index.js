var __defProp = Object.defineProperty;
var __name = (target, value) => __defProp(target, "name", { value, configurable: true });

// ../sdks/typescript/src/tokens.ts
var TokenInvariantError = class extends Error {
  static {
    __name(this, "TokenInvariantError");
  }
  name = "TokenInvariantError";
};
function assertNonNegative(name, value) {
  if (!Number.isInteger(value) || value < 0) {
    throw new TokenInvariantError(`${name} must be a non-negative integer, got ${value}`);
  }
}
__name(assertNonNegative, "assertNonNegative");
function tokenVector(v) {
  assertNonNegative("inputUncached", v.inputUncached);
  assertNonNegative("cacheRead", v.cacheRead);
  assertNonNegative("cacheWrite5m", v.cacheWrite5m);
  assertNonNegative("cacheWrite1h", v.cacheWrite1h);
  assertNonNegative("output", v.output);
  assertNonNegative("reasoning", v.reasoning);
  if (v.reasoning > v.output) {
    throw new TokenInvariantError(
      `reasoning (${v.reasoning}) must not exceed output (${v.output}); reasoning is derived and embedded within output (\xA75.2)`
    );
  }
  return Object.freeze({
    inputUncached: v.inputUncached,
    cacheRead: v.cacheRead,
    cacheWrite5m: v.cacheWrite5m,
    cacheWrite1h: v.cacheWrite1h,
    output: v.output,
    reasoning: v.reasoning
  });
}
__name(tokenVector, "tokenVector");

// ../sdks/typescript/src/terminal.ts
function asRecord(value) {
  if (typeof value === "object" && value !== null && !Array.isArray(value)) {
    return value;
  }
  return {};
}
__name(asRecord, "asRecord");
function asInt(value) {
  if (typeof value === "number" && Number.isFinite(value)) {
    const truncated = Math.trunc(value);
    return truncated > 0 ? truncated : 0;
  }
  return 0;
}
__name(asInt, "asInt");
var AnthropicStreamAccumulator = class {
  static {
    __name(this, "AnthropicStreamAccumulator");
  }
  cacheRead = 0;
  cacheWrite5m = 0;
  cacheWrite1h = 0;
  inputUncached = 0;
  outputTerminal = 0;
  thinkingBlocks = 0;
  sawMessageStart = false;
  cancelled = false;
  /** Fold one streaming event into the accumulator (idempotent on cache fields). */
  observe(event) {
    const eventType = event["type"];
    if (eventType === "message_start") {
      this.observeMessageStart(event);
    } else if (eventType === "message_delta") {
      this.observeMessageDelta(event);
    } else if (eventType === "content_block_start") {
      const block = asRecord(event["content_block"]);
      if (block["type"] === "thinking") {
        this.thinkingBlocks += 1;
      }
    }
  }
  observeMessageStart(event) {
    this.sawMessageStart = true;
    const usage = asRecord(asRecord(event["message"])["usage"]);
    this.inputUncached = asInt(usage["input_tokens"]);
    this.cacheRead = asInt(usage["cache_read_input_tokens"]);
    const cacheCreation = asRecord(usage["cache_creation"]);
    this.cacheWrite5m = asInt(cacheCreation["ephemeral_5m_input_tokens"]);
    this.cacheWrite1h = asInt(cacheCreation["ephemeral_1h_input_tokens"]);
    this.outputTerminal = asInt(usage["output_tokens"]);
  }
  observeMessageDelta(event) {
    const usage = asRecord(event["usage"]);
    if ("output_tokens" in usage) {
      this.outputTerminal = asInt(usage["output_tokens"]);
    }
  }
  /** Record that the stream was cancelled before its terminal message_stop. */
  markCancelled() {
    this.cancelled = true;
  }
  /** Build the terminal {@link TokenVector} (output >= reasoning by construction). */
  finalize() {
    const output = Math.max(this.outputTerminal, this.thinkingBlocks);
    return tokenVector({
      inputUncached: this.inputUncached,
      cacheRead: this.cacheRead,
      cacheWrite5m: this.cacheWrite5m,
      cacheWrite1h: this.cacheWrite1h,
      output,
      reasoning: this.thinkingBlocks
    });
  }
  /** Build the {@link AttemptObservation} for the emit path. */
  finalizeObservation(args) {
    const partial = this.cancelled || !this.sawMessageStart;
    return {
      provider: args.provider,
      model: args.model,
      tokens: this.finalize(),
      isStreaming: true,
      partialRecovered: partial
    };
  }
  /**
   * Build the observation for a NON-streaming response (full terminal usage in
   * one object): `isStreaming` and `partialRecovered` are both false.
   */
  finalizeObservationNonStreaming(args) {
    return {
      provider: args.provider,
      model: args.model,
      tokens: this.finalize(),
      isStreaming: false,
      partialRecovered: false
    };
  }
};
var OpenAIStreamAccumulator = class {
  static {
    __name(this, "OpenAIStreamAccumulator");
  }
  inputTotal = 0;
  cacheReadRaw = 0;
  output = 0;
  sawUsage = false;
  cancelled = false;
  includeUsage;
  constructor(args) {
    this.includeUsage = args.includeUsage;
  }
  /** Fold one streaming chunk; only the final chunk carries usage. */
  observe(chunk) {
    const usage = chunk["usage"];
    if (typeof usage !== "object" || usage === null || Array.isArray(usage)) {
      return;
    }
    const usageMap = usage;
    this.sawUsage = true;
    this.inputTotal = asInt(usageMap["prompt_tokens"]);
    const details = asRecord(usageMap["prompt_tokens_details"]);
    this.cacheReadRaw = asInt(details["cached_tokens"]);
    this.output = asInt(usageMap["completion_tokens"]);
  }
  /** Record that the stream was cancelled before the final usage chunk. */
  markCancelled() {
    this.cancelled = true;
  }
  /** Build the terminal {@link TokenVector} (uncached = prompt - cached). */
  finalize() {
    const cacheRead = Math.min(this.cacheReadRaw, this.inputTotal);
    return tokenVector({
      inputUncached: this.inputTotal - cacheRead,
      cacheRead,
      cacheWrite5m: 0,
      cacheWrite1h: 0,
      output: this.output,
      reasoning: 0
    });
  }
  /** Build the {@link AttemptObservation}; flag partial if usage never arrived. */
  finalizeObservation(args) {
    const partial = this.cancelled || !this.sawUsage || !this.includeUsage;
    return {
      provider: args.provider,
      model: args.model,
      tokens: this.finalize(),
      isStreaming: true,
      partialRecovered: partial
    };
  }
  /**
   * Build the observation for a NON-streaming response (usage present on the
   * single response object): `isStreaming` and `partialRecovered` are false.
   */
  finalizeObservationNonStreaming(args) {
    return {
      provider: args.provider,
      model: args.model,
      tokens: this.finalize(),
      isStreaming: false,
      partialRecovered: false
    };
  }
};
var GeminiStreamAccumulator = class {
  static {
    __name(this, "GeminiStreamAccumulator");
  }
  promptTokens = 0;
  cachedTokens = 0;
  candidatesTokens = 0;
  thoughtsTokens = 0;
  sawUsage = false;
  cancelled = false;
  /** Fold one streaming chunk; keep the latest cumulative usageMetadata. */
  observe(chunk) {
    const meta = chunk["usageMetadata"];
    if (typeof meta !== "object" || meta === null || Array.isArray(meta)) {
      return;
    }
    const m = meta;
    this.sawUsage = true;
    this.promptTokens = asInt(m["promptTokenCount"]);
    this.cachedTokens = asInt(m["cachedContentTokenCount"]);
    this.candidatesTokens = asInt(m["candidatesTokenCount"]);
    this.thoughtsTokens = asInt(m["thoughtsTokenCount"]);
  }
  /** Record that the stream was cancelled before the final usage chunk. */
  markCancelled() {
    this.cancelled = true;
  }
  /** Build the terminal {@link TokenVector} (uncached = prompt - cached). */
  finalize() {
    const cacheRead = Math.min(this.cachedTokens, this.promptTokens);
    return tokenVector({
      inputUncached: this.promptTokens - cacheRead,
      cacheRead,
      cacheWrite5m: 0,
      cacheWrite1h: 0,
      // candidates + thoughts are both billed as output; reasoning embedded within.
      output: this.candidatesTokens + this.thoughtsTokens,
      reasoning: this.thoughtsTokens
    });
  }
  /** Build the {@link AttemptObservation}; flag partial if usage never arrived. */
  finalizeObservation(args) {
    return {
      provider: args.provider,
      model: args.model,
      tokens: this.finalize(),
      isStreaming: true,
      partialRecovered: this.cancelled || !this.sawUsage
    };
  }
};

// src/capture.ts
function newAccumulator(provider, opts = {}) {
  switch (provider) {
    case "anthropic":
      return new AnthropicStreamAccumulator();
    case "gemini":
      return new GeminiStreamAccumulator();
    // OpenRouter speaks the OpenAI wire shape, so it accumulates identically. Its
    // authoritative `usage.cost` is read separately (see `readInlineCost`).
    case "openai":
    case "openrouter":
      return new OpenAIStreamAccumulator({
        includeUsage: opts.includeUsage ?? false
      });
  }
}
__name(newAccumulator, "newAccumulator");
function requestedStreamUsage(requestBody) {
  if (!requestBody) return false;
  try {
    const parsed = JSON.parse(requestBody);
    if (!parsed || typeof parsed !== "object") return false;
    const opts = parsed["stream_options"];
    return Boolean(asRecord2(opts)?.["include_usage"]);
  } catch {
    return false;
  }
}
__name(requestedStreamUsage, "requestedStreamUsage");
function foldSseChunk(acc, chunk, carry) {
  const buffer = carry + chunk;
  const lines = buffer.split("\n");
  const remainder = lines.pop() ?? "";
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed.startsWith("data:")) continue;
    const payload = trimmed.slice(5).trim();
    if (!payload || payload === "[DONE]") continue;
    try {
      const parsed = JSON.parse(payload);
      if (parsed && typeof parsed === "object") {
        acc.observe(parsed);
      }
    } catch {
    }
  }
  return remainder;
}
__name(foldSseChunk, "foldSseChunk");
function observeNonStreaming(provider, body, fallbackModel) {
  const model = asString(body["model"]) || fallbackModel;
  const usage = asRecord2(body["usage"]) ?? asRecord2(body["usageMetadata"]);
  if (!usage) return void 0;
  if (provider === "anthropic") {
    const cacheCreation = asRecord2(usage["cache_creation"]);
    return {
      provider,
      model,
      tokens: {
        inputUncached: asInt2(usage["input_tokens"]),
        cacheRead: asInt2(usage["cache_read_input_tokens"]),
        cacheWrite5m: asInt2(cacheCreation?.["ephemeral_5m_input_tokens"]),
        cacheWrite1h: asInt2(cacheCreation?.["ephemeral_1h_input_tokens"]),
        output: asInt2(usage["output_tokens"]),
        reasoning: 0
      },
      isStreaming: false,
      partialRecovered: false
    };
  }
  if (provider === "gemini") {
    const cached = asInt2(usage["cachedContentTokenCount"]);
    const prompt = asInt2(usage["promptTokenCount"]);
    return {
      provider,
      model,
      tokens: {
        inputUncached: Math.max(0, prompt - cached),
        cacheRead: cached,
        cacheWrite5m: 0,
        cacheWrite1h: 0,
        output: asInt2(usage["candidatesTokenCount"]),
        reasoning: asInt2(usage["thoughtsTokenCount"])
      },
      isStreaming: false,
      partialRecovered: false
    };
  }
  const details = asRecord2(usage["prompt_tokens_details"]);
  const cachedIn = asInt2(details?.["cached_tokens"]);
  const promptIn = asInt2(usage["prompt_tokens"]);
  const outDetails = asRecord2(usage["completion_tokens_details"]);
  return {
    provider,
    model,
    tokens: {
      inputUncached: Math.max(0, promptIn - cachedIn),
      cacheRead: cachedIn,
      cacheWrite5m: 0,
      cacheWrite1h: 0,
      output: asInt2(usage["completion_tokens"]),
      reasoning: asInt2(outDetails?.["reasoning_tokens"])
    },
    isStreaming: false,
    partialRecovered: false
  };
}
__name(observeNonStreaming, "observeNonStreaming");
function readInlineCost(body) {
  const usage = asRecord2(body["usage"]);
  if (!usage || usage["is_estimate"] === true) return void 0;
  const cost = usage["cost"];
  return typeof cost === "number" && Number.isFinite(cost) ? cost : void 0;
}
__name(readInlineCost, "readInlineCost");
function asRecord2(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : void 0;
}
__name(asRecord2, "asRecord");
function asString(value) {
  return typeof value === "string" ? value : "";
}
__name(asString, "asString");
function asInt2(value) {
  return typeof value === "number" && Number.isFinite(value) ? Math.trunc(value) : 0;
}
__name(asInt2, "asInt");

// src/headers.ts
var VMX_PREFIX = "x-vmx-";
var H_KEY = "x-vmx-key";
var H_RUN_ID = "x-vmx-run-id";
var H_AGENT = "x-vmx-agent";
var H_OUTCOME = "x-vmx-outcome";
var H_ENTITY_PREFIX = "x-vmx-entity-";
var H_BAGGAGE = "baggage";
var H_RUN_ID_ECHO = "x-vmx-run-id";
var BAGGAGE_RUN_ID_KEY = "valuemaxx.run_id";
function readIntent(headers, mintId) {
  const explicitRunId = headers.get(H_RUN_ID)?.trim();
  const baggageRunId = explicitRunId ? void 0 : parseBaggageRunId(headers.get(H_BAGGAGE));
  const carried = explicitRunId || baggageRunId;
  const entityKeys = {};
  for (const [name, value] of headers) {
    const lower = name.toLowerCase();
    if (!lower.startsWith(H_ENTITY_PREFIX) || !value) continue;
    const key = lower.slice(H_ENTITY_PREFIX.length).replaceAll("-", "_");
    if (key) entityKeys[key] = value;
  }
  return {
    key: headers.get(H_KEY)?.trim() || void 0,
    runId: carried || mintId(),
    runIdWasMinted: !carried,
    agentName: headers.get(H_AGENT)?.trim() || void 0,
    entityKeys,
    outcome: headers.get(H_OUTCOME)?.trim() || void 0
  };
}
__name(readIntent, "readIntent");
function parseBaggageRunId(raw) {
  if (!raw) return void 0;
  for (const member of raw.split(",")) {
    const eq = member.indexOf("=");
    if (eq < 0) continue;
    const key = member.slice(0, eq).trim();
    if (key !== BAGGAGE_RUN_ID_KEY) continue;
    const value = member.slice(eq + 1).split(";")[0]?.trim();
    if (value) return decodeURIComponent(value);
  }
  return void 0;
}
__name(parseBaggageRunId, "parseBaggageRunId");
function forwardableHeaders(headers) {
  const out = new Headers();
  for (const [name, value] of headers) {
    const lower = name.toLowerCase();
    if (lower.startsWith(VMX_PREFIX)) continue;
    if (lower === "host" || lower === "content-length") continue;
    if (lower === "accept-encoding") continue;
    out.set(name, value);
  }
  return out;
}
__name(forwardableHeaders, "forwardableHeaders");

// ../sdks/typescript/src/semconv.ts
var GEN_AI_SYSTEM = "gen_ai.system";
var GEN_AI_REQUEST_MODEL = "gen_ai.request.model";
var GEN_AI_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens";
var GEN_AI_USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens";
var AI_MARGIN_CACHE_READ = "ai_margin.usage.cache_read_tokens";
var AI_MARGIN_CACHE_WRITE_5M = "ai_margin.usage.cache_write_5m_tokens";
var AI_MARGIN_CACHE_WRITE_1H = "ai_margin.usage.cache_write_1h_tokens";
var AI_MARGIN_REASONING = "ai_margin.usage.reasoning_tokens";
var AI_MARGIN_RUN_ID = "ai_margin.run_id";
var AI_MARGIN_ATTEMPT_ID = "ai_margin.attempt_id";
var AI_MARGIN_TENANT_ID = "ai_margin.tenant_id";
var AI_MARGIN_AGENT_NAME = "ai_margin.agent_name";
var AI_MARGIN_ENTITY_PREFIX = "ai_margin.entity.";
var AI_MARGIN_PROVENANCE = "ai_margin.provenance";
var AI_MARGIN_CAPTURE_GRANULARITY = "ai_margin.capture_granularity";
var AI_MARGIN_COST_USD = "ai_margin.cost_usd";
var AI_MARGIN_IS_STREAMING = "ai_margin.is_streaming";
var AI_MARGIN_PARTIAL_RECOVERED = "ai_margin.partial_recovered";
var ALL_KEYS = Object.freeze(
  [
    GEN_AI_SYSTEM,
    GEN_AI_REQUEST_MODEL,
    GEN_AI_USAGE_INPUT_TOKENS,
    GEN_AI_USAGE_OUTPUT_TOKENS,
    AI_MARGIN_CACHE_READ,
    AI_MARGIN_CACHE_WRITE_5M,
    AI_MARGIN_CACHE_WRITE_1H,
    AI_MARGIN_REASONING,
    AI_MARGIN_RUN_ID,
    AI_MARGIN_ATTEMPT_ID,
    AI_MARGIN_TENANT_ID,
    AI_MARGIN_PROVENANCE,
    AI_MARGIN_CAPTURE_GRANULARITY,
    AI_MARGIN_COST_USD,
    AI_MARGIN_IS_STREAMING,
    AI_MARGIN_PARTIAL_RECOVERED
  ].sort()
);

// src/report.ts
async function reportSpan(backend, intent, observation, opts = {}) {
  const { tokens } = observation;
  const attributes = {
    [GEN_AI_SYSTEM]: observation.provider,
    [GEN_AI_REQUEST_MODEL]: observation.model,
    [GEN_AI_USAGE_INPUT_TOKENS]: tokens.inputUncached,
    [GEN_AI_USAGE_OUTPUT_TOKENS]: tokens.output,
    [AI_MARGIN_CACHE_READ]: tokens.cacheRead,
    [AI_MARGIN_CACHE_WRITE_5M]: tokens.cacheWrite5m,
    [AI_MARGIN_CACHE_WRITE_1H]: tokens.cacheWrite1h,
    [AI_MARGIN_REASONING]: tokens.reasoning,
    [AI_MARGIN_RUN_ID]: intent.runId,
    // One attempt per proxied request. A retry the host makes is a new request and
    // therefore a new attempt, which is what dedup on (run, attempt) expects.
    [AI_MARGIN_ATTEMPT_ID]: crypto.randomUUID(),
    [AI_MARGIN_IS_STREAMING]: observation.isStreaming,
    [AI_MARGIN_PARTIAL_RECOVERED]: observation.partialRecovered
  };
  if (intent.agentName) {
    attributes[AI_MARGIN_AGENT_NAME] = intent.agentName;
  }
  for (const [name, value] of Object.entries(intent.entityKeys)) {
    attributes[`${AI_MARGIN_ENTITY_PREFIX}${name}`] = value;
  }
  if (opts.inlineCostUsd !== void 0) {
    attributes[AI_MARGIN_COST_USD] = opts.inlineCostUsd;
    attributes[AI_MARGIN_PROVENANCE] = "provider_reconciled";
  }
  await post(backend, "/ingest_otlp_span", intent.key, { attributes });
}
__name(reportSpan, "reportSpan");
async function reportOutcome(backend, intent) {
  const entity = Object.keys(intent.entityKeys).length ? { entity: intent.entityKeys } : {};
  await post(
    backend,
    "/outcome",
    intent.key,
    { name: intent.outcome, run_id: intent.runId, source: "gateway", ...entity },
    { [BAGGAGE_RUN_ID_KEY]: intent.runId }
  );
}
__name(reportOutcome, "reportOutcome");
async function post(backend, path, key, body, baggage) {
  if (!key) return;
  const headers = {
    "content-type": "application/json",
    "x-api-key": key
  };
  if (baggage) {
    headers["baggage"] = Object.entries(baggage).map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join(",");
  }
  try {
    await fetch(`${backend.replace(/\/+$/, "")}${path}`, {
      method: "POST",
      headers,
      body: JSON.stringify(body)
    });
  } catch {
  }
}
__name(post, "post");

// src/index.ts
var ROUTES = [
  { prefix: "/openai", provider: "openai", upstream: "https://api.openai.com" },
  {
    prefix: "/anthropic",
    provider: "anthropic",
    upstream: "https://api.anthropic.com"
  },
  {
    prefix: "/gemini",
    provider: "gemini",
    upstream: "https://generativelanguage.googleapis.com"
  },
  {
    prefix: "/openrouter",
    provider: "openrouter",
    upstream: "https://openrouter.ai/api"
  }
];
var src_default = {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname === "/healthz") {
      return new Response("ok", { status: 200 });
    }
    if (url.pathname === "/v1/outcome" && request.method === "POST") {
      return forwardOutcome(request, env);
    }
    const route = ROUTES.find(
      (r) => url.pathname === r.prefix || url.pathname.startsWith(`${r.prefix}/`)
    );
    if (!route) {
      return json(
        {
          error: "unknown_route",
          message: `No provider route matches ${url.pathname}. Expected one of: ${ROUTES.map((r) => r.prefix).join(", ")}`
        },
        404
      );
    }
    const upstreamUrl = new URL(
      url.pathname.slice(route.prefix.length) + url.search,
      route.upstream
    );
    try {
      return await proxy(request, upstreamUrl, route.provider, env, ctx);
    } catch {
      return fetch(
        new Request(upstreamUrl, {
          method: request.method,
          headers: forwardableHeaders(request.headers),
          body: request.body
        })
      );
    }
  }
};
async function forwardOutcome(request, env) {
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
      body
    }
  );
  return new Response(upstream.body, {
    status: upstream.status,
    headers: { "content-type": "application/json" }
  });
}
__name(forwardOutcome, "forwardOutcome");
async function proxy(request, upstreamUrl, provider, env, ctx) {
  const intent = readIntent(request.headers, () => crypto.randomUUID());
  const requestBody = request.method === "GET" || request.method === "HEAD" ? void 0 : await request.text();
  const requestedModel = readModel(requestBody);
  const upstream = await fetch(
    new Request(upstreamUrl, {
      method: request.method,
      headers: forwardableHeaders(request.headers),
      ...requestBody === void 0 ? {} : { body: requestBody }
    })
  );
  if (!intent.key || !upstream.body) {
    return withEcho(upstream, intent);
  }
  const [toClient, toCapture] = upstream.body.tee();
  const isStream = (upstream.headers.get("content-type") ?? "").includes(
    "text/event-stream"
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
      status: upstream.status
    })
  );
  return withEcho(
    new Response(toClient, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: upstream.headers
    }),
    intent
  );
}
__name(proxy, "proxy");
function withEcho(response, intent) {
  if (!intent.runIdWasMinted) return response;
  const headers = new Headers(response.headers);
  headers.set(H_RUN_ID_ECHO, intent.runId);
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers
  });
}
__name(withEcho, "withEcho");
async function capture(args) {
  const { stream, isStream, provider, model, includeUsage, intent, env, status } = args;
  try {
    const observation = isStream ? await readStreaming(stream, provider, model, includeUsage) : await readNonStreaming(stream, provider, model);
    if (observation) {
      await reportSpan(env.VALUEMAXX_BACKEND, intent, observation.observation, {
        ...observation.inlineCostUsd === void 0 ? {} : { inlineCostUsd: observation.inlineCostUsd }
      });
    }
    if (intent.outcome && status >= 200 && status < 300) {
      await reportOutcome(env.VALUEMAXX_BACKEND, intent);
    }
  } catch {
  }
}
__name(capture, "capture");
async function readStreaming(stream, provider, model, includeUsage) {
  const acc = newAccumulator(provider, { includeUsage });
  const reader = stream.pipeThrough(new TextDecoderStream()).getReader();
  let carry = "";
  let complete = false;
  try {
    for (; ; ) {
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
  if (!complete) acc.markCancelled();
  return { observation: acc.finalizeObservation({ provider, model }) };
}
__name(readStreaming, "readStreaming");
async function readNonStreaming(stream, provider, model) {
  const text = await new Response(stream).text();
  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch {
    return void 0;
  }
  if (!parsed || typeof parsed !== "object") return void 0;
  const body = parsed;
  const observation = observeNonStreaming(provider, body, model);
  if (!observation) return void 0;
  const inlineCostUsd = provider === "openrouter" ? readInlineCost(body) : void 0;
  return {
    observation,
    ...inlineCostUsd === void 0 ? {} : { inlineCostUsd }
  };
}
__name(readNonStreaming, "readNonStreaming");
function readModel(requestBody) {
  if (!requestBody) return "";
  try {
    const parsed = JSON.parse(requestBody);
    if (parsed && typeof parsed === "object") {
      const model = parsed["model"];
      if (typeof model === "string") return model;
    }
  } catch {
  }
  return "";
}
__name(readModel, "readModel");
function json(body, status) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" }
  });
}
__name(json, "json");

// node_modules/wrangler/templates/middleware/middleware-ensure-req-body-drained.ts
var drainBody = /* @__PURE__ */ __name(async (request, env, _ctx, middlewareCtx) => {
  try {
    return await middlewareCtx.next(request, env);
  } finally {
    try {
      if (request.body !== null && !request.bodyUsed) {
        const reader = request.body.getReader();
        while (!(await reader.read()).done) {
        }
      }
    } catch (e) {
      console.error("Failed to drain the unused request body.", e);
    }
  }
}, "drainBody");
var middleware_ensure_req_body_drained_default = drainBody;

// node_modules/wrangler/templates/middleware/middleware-miniflare3-json-error.ts
function reduceError(e) {
  return {
    name: e?.name,
    message: e?.message ?? String(e),
    stack: e?.stack,
    cause: e?.cause === void 0 ? void 0 : reduceError(e.cause)
  };
}
__name(reduceError, "reduceError");
var jsonError = /* @__PURE__ */ __name(async (request, env, _ctx, middlewareCtx) => {
  try {
    return await middlewareCtx.next(request, env);
  } catch (e) {
    const error = reduceError(e);
    const body = JSON.stringify(error);
    const headers = {
      "Content-Type": "application/json",
      "MF-Experimental-Error-Stack": "true"
    };
    const encoded = encodeURIComponent(body);
    if (encoded.length <= 8192) {
      headers["MF-Experimental-Error-Stack-Payload"] = encoded;
    }
    return new Response(body, { status: 500, headers });
  }
}, "jsonError");
var middleware_miniflare3_json_error_default = jsonError;

// .wrangler/tmp/bundle-qPk9G4/middleware-insertion-facade.js
var __INTERNAL_WRANGLER_MIDDLEWARE__ = [
  middleware_ensure_req_body_drained_default,
  middleware_miniflare3_json_error_default
];
var middleware_insertion_facade_default = src_default;

// node_modules/wrangler/templates/middleware/common.ts
var __facade_middleware__ = [];
function __facade_register__(...args) {
  __facade_middleware__.push(...args.flat());
}
__name(__facade_register__, "__facade_register__");
function __facade_invokeChain__(request, env, ctx, dispatch, middlewareChain) {
  const [head, ...tail] = middlewareChain;
  const middlewareCtx = {
    dispatch,
    next(newRequest, newEnv) {
      return __facade_invokeChain__(newRequest, newEnv, ctx, dispatch, tail);
    }
  };
  return head(request, env, ctx, middlewareCtx);
}
__name(__facade_invokeChain__, "__facade_invokeChain__");
function __facade_invoke__(request, env, ctx, dispatch, finalMiddleware) {
  return __facade_invokeChain__(request, env, ctx, dispatch, [
    ...__facade_middleware__,
    finalMiddleware
  ]);
}
__name(__facade_invoke__, "__facade_invoke__");

// .wrangler/tmp/bundle-qPk9G4/middleware-loader.entry.ts
var __Facade_ScheduledController__ = class ___Facade_ScheduledController__ {
  constructor(scheduledTime, cron, noRetry) {
    this.scheduledTime = scheduledTime;
    this.cron = cron;
    this.#noRetry = noRetry;
  }
  scheduledTime;
  cron;
  static {
    __name(this, "__Facade_ScheduledController__");
  }
  #noRetry;
  noRetry() {
    if (!(this instanceof ___Facade_ScheduledController__)) {
      throw new TypeError("Illegal invocation");
    }
    this.#noRetry();
  }
};
function wrapExportedHandler(worker) {
  if (__INTERNAL_WRANGLER_MIDDLEWARE__ === void 0 || __INTERNAL_WRANGLER_MIDDLEWARE__.length === 0) {
    return worker;
  }
  for (const middleware of __INTERNAL_WRANGLER_MIDDLEWARE__) {
    __facade_register__(middleware);
  }
  const fetchDispatcher = /* @__PURE__ */ __name(function(request, env, ctx) {
    if (worker.fetch === void 0) {
      throw new Error("Handler does not export a fetch() function.");
    }
    return worker.fetch(request, env, ctx);
  }, "fetchDispatcher");
  return {
    ...worker,
    fetch(request, env, ctx) {
      const dispatcher = /* @__PURE__ */ __name(function(type, init) {
        if (type === "scheduled" && worker.scheduled !== void 0) {
          const controller = new __Facade_ScheduledController__(
            Date.now(),
            init.cron ?? "",
            () => {
            }
          );
          return worker.scheduled(controller, env, ctx);
        }
      }, "dispatcher");
      return __facade_invoke__(request, env, ctx, dispatcher, fetchDispatcher);
    }
  };
}
__name(wrapExportedHandler, "wrapExportedHandler");
function wrapWorkerEntrypoint(klass) {
  if (__INTERNAL_WRANGLER_MIDDLEWARE__ === void 0 || __INTERNAL_WRANGLER_MIDDLEWARE__.length === 0) {
    return klass;
  }
  for (const middleware of __INTERNAL_WRANGLER_MIDDLEWARE__) {
    __facade_register__(middleware);
  }
  return class extends klass {
    #fetchDispatcher = /* @__PURE__ */ __name((request, env, ctx) => {
      this.env = env;
      this.ctx = ctx;
      if (super.fetch === void 0) {
        throw new Error("Entrypoint class does not define a fetch() function.");
      }
      return super.fetch(request);
    }, "#fetchDispatcher");
    #dispatcher = /* @__PURE__ */ __name((type, init) => {
      if (type === "scheduled" && super.scheduled !== void 0) {
        const controller = new __Facade_ScheduledController__(
          Date.now(),
          init.cron ?? "",
          () => {
          }
        );
        return super.scheduled(controller);
      }
    }, "#dispatcher");
    fetch(request) {
      return __facade_invoke__(
        request,
        this.env,
        this.ctx,
        this.#dispatcher,
        this.#fetchDispatcher
      );
    }
  };
}
__name(wrapWorkerEntrypoint, "wrapWorkerEntrypoint");
var WRAPPED_ENTRY;
if (typeof middleware_insertion_facade_default === "object") {
  WRAPPED_ENTRY = wrapExportedHandler(middleware_insertion_facade_default);
} else if (typeof middleware_insertion_facade_default === "function") {
  WRAPPED_ENTRY = wrapWorkerEntrypoint(middleware_insertion_facade_default);
}
var middleware_loader_entry_default = WRAPPED_ENTRY;
export {
  __INTERNAL_WRANGLER_MIDDLEWARE__,
  middleware_loader_entry_default as default
};
//# sourceMappingURL=index.js.map
