/**
 * valuemaxx — AI Margin Intelligence, the one-line, fail-open Node SDK (§5.1).
 *
 * ```ts
 * import { init } from "valuemaxx";
 * init({ tenantId, ingestKey, endpoint });
 * ```
 *
 * `init()` installs real OpenTelemetry instrumentation for the OpenAI / Anthropic
 * Node clients (a purpose-built, instance-scoped monkey-patch — not a shim) plus
 * an OTLP/HTTP exporter; for the Vercel AI SDK it hands you a tracer to pass via
 * `experimental_telemetry`. Streaming cost is accumulated to TERMINAL token
 * values across chunks before the cost span is emitted. It NEVER throws into the
 * host call path (H9). The emitted OTLP keys are byte-identical to the Python
 * SDK's (a single cross-language wire contract).
 */

export { init } from "./init.js";
export type {
  ClientTarget,
  EffectiveConfigEcho,
  InitOptions,
  InitResult,
} from "./init.js";

export { run, activeRunId, track } from "./run.js";

export {
  InitConfigError,
  SecretString,
  resolveConfig,
} from "./config.js";
export type { EffectiveConfig, InitConfig } from "./config.js";

export {
  AnthropicStreamAccumulator,
  OpenAIStreamAccumulator,
} from "./terminal.js";

export {
  tokenVector,
  tokenVectorFromProvider,
  totalInput,
  TokenInvariantError,
} from "./tokens.js";
export type { TokenVector } from "./tokens.js";

export type { AttemptObservation } from "./observation.js";

export { buildSpanAttributes } from "./emit.js";
export type { SpanIdentity } from "./emit.js";

export {
  versionSelftest,
  rangeContains,
  KNOWN_GOOD,
} from "./selftest.js";
export type {
  CaptureGranularity,
  SelfTestResult,
  SupportedRange,
} from "./selftest.js";

export {
  instrumentMethod,
  extractNonStreaming,
} from "./instrumentation.js";
export type {
  InstrumentDeps,
  InstrumentHandle,
  Provider,
} from "./instrumentation.js";

export * as semconv from "./semconv.js";
export { ALL_KEYS } from "./semconv.js";
