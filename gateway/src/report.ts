/**
 * Reporting to the backend — cost spans and outcomes, out of band.
 *
 * Both calls happen inside `waitUntil`, after the client already holds its response,
 * so neither can add latency to the proxied request. Both swallow failures: the
 * backend being down must degrade telemetry, never the user's LLM call.
 *
 * The wire format is the one the backend already speaks (`/ingest_otlp_span` with
 * `gen_ai.*` / `ai_margin.*` attributes), so the gateway is just another producer.
 * Nothing server-side had to learn about proxies.
 */

import type { AttemptObservation } from "../../sdks/typescript/src/observation.js";
import * as semconv from "../../sdks/typescript/src/semconv.js";
import type { ConfigIdentity } from "./config.js";
import { BAGGAGE_RUN_ID_KEY, type CaptureIntent } from "./headers.js";

/** Ship one captured attempt to the backend's span ingest. */
export async function reportSpan(
  backend: string,
  intent: CaptureIntent,
  observation: AttemptObservation,
  opts: {
    inlineCostUsd?: number;
    latencyMs?: number;
    status?: number;
    configIdentity?: ConfigIdentity;
  } = {},
): Promise<void> {
  const { tokens } = observation;
  const attributes: Record<string, string | number | boolean> = {
    [semconv.GEN_AI_SYSTEM]: observation.provider,
    [semconv.GEN_AI_REQUEST_MODEL]: observation.model,
    [semconv.GEN_AI_USAGE_INPUT_TOKENS]: tokens.inputUncached,
    [semconv.GEN_AI_USAGE_OUTPUT_TOKENS]: tokens.output,
    [semconv.AI_MARGIN_CACHE_READ]: tokens.cacheRead,
    [semconv.AI_MARGIN_CACHE_WRITE_5M]: tokens.cacheWrite5m,
    [semconv.AI_MARGIN_CACHE_WRITE_1H]: tokens.cacheWrite1h,
    [semconv.AI_MARGIN_REASONING]: tokens.reasoning,
    [semconv.AI_MARGIN_RUN_ID]: intent.runId,
    // One attempt per proxied request. A retry the host makes is a new request and
    // therefore a new attempt, which is what dedup on (run, attempt) expects.
    [semconv.AI_MARGIN_ATTEMPT_ID]: crypto.randomUUID(),
    [semconv.AI_MARGIN_IS_STREAMING]: observation.isStreaming,
    [semconv.AI_MARGIN_PARTIAL_RECOVERED]: observation.partialRecovered,
  };

  if (intent.agentName) {
    attributes[semconv.AI_MARGIN_AGENT_NAME] = intent.agentName;
  }
  if (opts.latencyMs !== undefined) {
    attributes[semconv.AI_MARGIN_LATENCY_MS] = opts.latencyMs;
  }
  if (opts.status !== undefined) {
    attributes[semconv.AI_MARGIN_HTTP_STATUS] = opts.status;
  }
  if (intent.callSiteId) {
    attributes[semconv.AI_MARGIN_CALL_SITE_ID] = intent.callSiteId;
  }
  if (opts.configIdentity) {
    attributes[semconv.AI_MARGIN_SYSTEM_HASH] = opts.configIdentity.systemHash;
    attributes[semconv.AI_MARGIN_TOOLS_HASH] = opts.configIdentity.toolsHash;
    attributes[semconv.AI_MARGIN_PARAMS_HASH] = opts.configIdentity.paramsHash;
    attributes[semconv.AI_MARGIN_CONFIG_IDENTITY] = opts.configIdentity.configId;
    // This is the request-local raw system identity. A stateful template learner can
    // later replace it with a strong identity; never overclaim that work here.
    attributes[semconv.AI_MARGIN_CONFIG_IDENTITY_WEAK] = true;
  }
  // Recorded with no engine reading them: a variant stamp is impossible to add to
  // traffic after it has already run, so history has to carry it from the start.
  if (intent.experiment) {
    attributes[semconv.AI_MARGIN_EXPERIMENT] = intent.experiment;
  }
  if (intent.variant) {
    attributes[semconv.AI_MARGIN_VARIANT] = intent.variant;
  }
  if (intent.app) {
    attributes[semconv.AI_MARGIN_APP] = intent.app;
  }
  for (const [name, value] of Object.entries(intent.entityKeys)) {
    attributes[`${semconv.AI_MARGIN_ENTITY_PREFIX}${name}`] = value;
  }
  // An authoritative billed cost (OpenRouter) is reconciled truth, not an estimate
  // off a price card — say so, so the honesty axis stays accurate downstream.
  if (opts.inlineCostUsd !== undefined) {
    attributes[semconv.AI_MARGIN_COST_USD] = opts.inlineCostUsd;
    attributes[semconv.AI_MARGIN_PROVENANCE] = "provider_reconciled";
  }

  await post(backend, "/ingest_otlp_span", intent.key, { attributes });
}

/**
 * Record the outcome the caller declared with `x-vmx-outcome`.
 *
 * The run id rides the W3C `baggage` header rather than the body: that is the
 * backend's T2 channel, and it means the binding tier is decided server-side by the
 * cascade. A caller states what happened; it never states how much to trust the link.
 */
export async function reportOutcome(
  backend: string,
  intent: CaptureIntent,
): Promise<void> {
  const entity = Object.keys(intent.entityKeys).length
    ? { entity: intent.entityKeys }
    : {};
  await post(
    backend,
    "/outcome",
    intent.key,
    { name: intent.outcome, run_id: intent.runId, source: "gateway", ...entity },
    { [BAGGAGE_RUN_ID_KEY]: intent.runId },
  );
}

async function post(
  backend: string,
  path: string,
  key: string | undefined,
  body: unknown,
  baggage?: Record<string, string>,
): Promise<void> {
  if (!key) return;
  const headers: Record<string, string> = {
    "content-type": "application/json",
    "x-api-key": key,
  };
  if (baggage) {
    headers["baggage"] = Object.entries(baggage)
      .map(([k, v]) => `${k}=${encodeURIComponent(v)}`)
      .join(",");
  }
  try {
    await fetch(`${backend.replace(/\/+$/, "")}${path}`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });
  } catch {
    // Telemetry is best-effort by construction. The caller's request is already done.
  }
}
