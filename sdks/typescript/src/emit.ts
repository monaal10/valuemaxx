/**
 * Map an {@link AttemptObservation} onto the OTLP semconv attribute keys (§5.2).
 *
 * Every key is read from the {@link import("./semconv.js")} constants — never an
 * inline literal — so the wire contract has exactly one source of truth shared
 * with the Python SDK. The resulting attribute bag is what the SDK stamps on the
 * cost span before the OTLP exporter ships it.
 */

import type { Attributes } from "@opentelemetry/api";

import type { AttemptObservation } from "./observation.js";
import type { CaptureGranularity } from "./selftest.js";
import * as semconv from "./semconv.js";
import { totalInput } from "./tokens.js";

/** Identity + capture metadata that rides every cost span alongside the usage. */
export interface SpanIdentity {
  readonly tenantId: string;
  readonly runId: string;
  readonly attemptId: string;
  readonly granularity: CaptureGranularity;
}

/**
 * Build the OTLP attribute bag for one cost span from an observation + identity.
 *
 * Cost is intentionally NOT computed here — the TS SDK emits the token vector
 * and the ingest reconciles cost from the pricebook (the universal OTLP path,
 * PG4). Provenance is always `measured` for client-side instrumentation.
 */
export function buildSpanAttributes(
  observation: AttemptObservation,
  identity: SpanIdentity,
): Attributes {
  const { tokens } = observation;
  return {
    [semconv.GEN_AI_SYSTEM]: observation.provider,
    [semconv.GEN_AI_REQUEST_MODEL]: observation.model,
    [semconv.GEN_AI_USAGE_INPUT_TOKENS]: totalInput(tokens),
    [semconv.GEN_AI_USAGE_OUTPUT_TOKENS]: tokens.output,
    [semconv.AI_MARGIN_CACHE_READ]: tokens.cacheRead,
    [semconv.AI_MARGIN_CACHE_WRITE_5M]: tokens.cacheWrite5m,
    [semconv.AI_MARGIN_CACHE_WRITE_1H]: tokens.cacheWrite1h,
    [semconv.AI_MARGIN_REASONING]: tokens.reasoning,
    [semconv.AI_MARGIN_RUN_ID]: identity.runId,
    [semconv.AI_MARGIN_ATTEMPT_ID]: identity.attemptId,
    [semconv.AI_MARGIN_TENANT_ID]: identity.tenantId,
    [semconv.AI_MARGIN_PROVENANCE]: "measured",
    [semconv.AI_MARGIN_CAPTURE_GRANULARITY]: identity.granularity,
    [semconv.AI_MARGIN_IS_STREAMING]: observation.isStreaming,
    [semconv.AI_MARGIN_PARTIAL_RECOVERED]: observation.partialRecovered,
  };
}
