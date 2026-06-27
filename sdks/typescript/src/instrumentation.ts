/**
 * Real OTel instrumentation for the OpenAI / Anthropic / Google GenAI Node clients
 * (§5.1, H1).
 *
 * These Node SDKs do not natively emit OTel spans, so this is a purpose-built
 * monkey-patch — NOT a shim. We wrap the INJECTED client's own completion method on
 * the **instance** (OpenAI/Anthropic `create`; Google `generateContent` /
 * `generateContentStream`), never the module/class, so an unrelated client in the same
 * process is completely untouched and capture is cleanly reversible. Mirrors the Python
 * instance-scoped transport patch.
 *
 * Everything off the host call path is wrapped in a fail-open guard: the host's
 * `create()` result (or its thrown error) always propagates untouched; any
 * internal capture error is caught, logged, and counted — never re-thrown into
 * the host (H9).
 *
 * For the Vercel AI SDK the host does not call our patch at all — it injects our
 * tracer via `experimental_telemetry` ({@link import("./init.js")} returns it).
 */

import type { Tracer } from "@opentelemetry/api";

import { buildSpanAttributes, type SpanIdentity } from "./emit.js";
import type { AttemptObservation } from "./observation.js";
import { activeRunId } from "./run.js";
import type { CaptureGranularity } from "./selftest.js";
import {
  AnthropicStreamAccumulator,
  GeminiStreamAccumulator,
  OpenAIStreamAccumulator,
} from "./terminal.js";
import { tokenVector } from "./tokens.js";

const UNBOUND_RUN_PREFIX = "unbound:";

/** Injected dependencies the instrumentation needs to emit a cost span. */
export interface InstrumentDeps {
  readonly tracer: Tracer;
  readonly tenantId: string;
  readonly granularity: CaptureGranularity;
  readonly newId: () => string;
  readonly logger: Pick<Console, "warn" | "error">;
}

/** A reversible handle over one instrumented client method. */
export interface InstrumentHandle {
  /** Remove the wrapper and restore the original method (idempotent). */
  uninstrument(): void;
  /** How many capture attempts were dropped/suppressed by the fail-open guard. */
  readonly dropped: number;
}

/** Emit one cost span from a finished observation; binds the ambient run id. */
function emitSpan(observation: AttemptObservation, deps: InstrumentDeps): void {
  const runId = activeRunId() ?? `${UNBOUND_RUN_PREFIX}${deps.newId()}`;
  const identity: SpanIdentity = {
    tenantId: deps.tenantId,
    runId,
    attemptId: deps.newId(),
    granularity: deps.granularity,
  };
  const span = deps.tracer.startSpan(`gen_ai.${observation.provider}`, {
    attributes: buildSpanAttributes(observation, identity),
  });
  span.end();
}

/**
 * An async iterable wrapper that folds each chunk into `accumulator`, then emits
 * the terminal cost span exactly once the stream is exhausted or cancelled.
 *
 * The original stream's values pass through untouched — the host iterates the
 * provider's chunks exactly as before; we only observe them.
 */
async function* observeStream<T extends Record<string, unknown>>(
  source: AsyncIterable<T>,
  accumulator: { observe: (chunk: Record<string, unknown>) => void; markCancelled: () => void },
  onTerminal: () => void,
  logger: Pick<Console, "warn">,
): AsyncIterable<T> {
  let completed = false;
  try {
    for await (const chunk of source) {
      try {
        accumulator.observe(chunk);
      } catch (err: unknown) {
        // capture must never break iteration of the host's stream.
        logger.warn("valuemaxx: suppressed a streaming-accumulator error (fail-open)", err);
      }
      yield chunk;
    }
    completed = true;
  } finally {
    if (!completed) {
      accumulator.markCancelled();
    }
    onTerminal();
  }
}

type CreateFn = (...args: unknown[]) => unknown;

/** Read a string property off an untyped args object, or "" when absent. */
function strProp(obj: unknown, key: string): string {
  if (typeof obj === "object" && obj !== null && key in obj) {
    const value = (obj as Record<string, unknown>)[key];
    return typeof value === "string" ? value : "";
  }
  return "";
}

/** Whether the first create() argument requested a streaming response. */
function isStreamingRequest(args: unknown[]): boolean {
  const first = args[0];
  return (
    typeof first === "object" &&
    first !== null &&
    (first as Record<string, unknown>)["stream"] === true
  );
}

/** Whether the request opted into OpenAI usage on the final chunk. */
function hasIncludeUsage(args: unknown[]): boolean {
  const first = args[0];
  if (typeof first !== "object" || first === null) {
    return false;
  }
  const opts = (first as Record<string, unknown>)["stream_options"];
  return (
    typeof opts === "object" &&
    opts !== null &&
    (opts as Record<string, unknown>)["include_usage"] === true
  );
}

/** The provider family of a client (drives which accumulator/extractor we use). */
export type Provider = "openai" | "anthropic" | "google";

interface WrapTarget {
  /** The object owning the `create` method (e.g. `client.chat.completions`). */
  readonly owner: Record<string, unknown>;
  /** The method name to wrap (almost always `"create"`). */
  readonly method: string;
  readonly provider: Provider;
}

/**
 * Wrap one `create`-style method on an instance, INSTANCE-scoped + reversible.
 *
 * The wrapper calls the host method first (outside the guard, so its result and
 * any thrown error propagate untouched), then captures off-path inside a
 * fail-open guard. Streaming responses are observed lazily via a pass-through
 * async iterable; non-streaming responses are read for terminal usage directly.
 */
export function instrumentMethod(target: WrapTarget, deps: InstrumentDeps): InstrumentHandle {
  const original = target.owner[target.method];
  if (typeof original !== "function") {
    throw new TypeError(
      `valuemaxx: cannot instrument ${target.method}; it is not a function on the given client`,
    );
  }
  const originalFn = original as CreateFn;
  let dropped = 0;
  let active = true;

  const wrapper = function (this: unknown, ...args: unknown[]): unknown {
    // (1) HOST CALL — outside the guard: its result/exception must propagate.
    const result = originalFn.apply(this, args);

    // (2) CAPTURE — inside a fail-open guard: never breaks the host.
    try {
      const streaming = isStreamingRequest(args);
      const model = strProp(args[0], "model");

      if (streaming) {
        return captureStream(result, args, model, target.provider, deps, () => {
          dropped += 1;
        });
      }

      // Non-streaming: usage lives on the awaited result; observe off-path.
      if (result instanceof Promise) {
        return result.then((value: unknown) => {
          try {
            const observation = extractNonStreaming(value, model, target.provider);
            if (observation !== null) {
              emitSpan(observation, deps);
            }
          } catch (err: unknown) {
            dropped += 1;
            deps.logger.warn("valuemaxx: suppressed a capture error (fail-open)", err);
          }
          return value;
        });
      }
      return result;
    } catch (err: unknown) {
      dropped += 1;
      deps.logger.warn("valuemaxx: suppressed a capture error (fail-open)", err);
      return result;
    }
  };

  target.owner[target.method] = wrapper;

  return {
    uninstrument(): void {
      if (!active) {
        return;
      }
      target.owner[target.method] = originalFn;
      active = false;
    },
    get dropped(): number {
      return dropped;
    },
  };
}

/** Wrap a streaming result in a pass-through observer that emits on terminal. */
function captureStream(
  result: unknown,
  args: unknown[],
  model: string,
  provider: Provider,
  deps: InstrumentDeps,
  onDrop: () => void,
): unknown {
  const accumulator =
    provider === "anthropic"
      ? new AnthropicStreamAccumulator()
      : provider === "google"
        ? new GeminiStreamAccumulator()
        : new OpenAIStreamAccumulator({ includeUsage: hasIncludeUsage(args) });

  const onTerminal = (): void => {
    try {
      const observation = accumulator.finalizeObservation({ provider, model });
      emitSpan(observation, deps);
    } catch (err: unknown) {
      onDrop();
      deps.logger.warn("valuemaxx: suppressed a streaming finalize error (fail-open)", err);
    }
  };

  if (isAsyncIterable(result)) {
    return observeStream(result, accumulator, onTerminal, deps.logger);
  }
  // Some clients return a Promise<Stream>; unwrap then observe.
  if (result instanceof Promise) {
    return result.then((value: unknown) => {
      if (isAsyncIterable(value)) {
        return observeStream(value, accumulator, onTerminal, deps.logger);
      }
      return value;
    });
  }
  return result;
}

function isAsyncIterable(value: unknown): value is AsyncIterable<Record<string, unknown>> {
  return (
    typeof value === "object" &&
    value !== null &&
    Symbol.asyncIterator in value &&
    typeof (value as { [Symbol.asyncIterator]?: unknown })[Symbol.asyncIterator] === "function"
  );
}

/** Coerce a possibly-undefined numeric usage field to a non-negative int. */
function usageInt(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) && value > 0 ? Math.floor(value) : 0;
}

/**
 * Pull terminal usage off a non-streaming Gemini response (`usageMetadata`).
 *
 * Gemini's `promptTokenCount` is the TOTAL input inclusive of cached content, so
 * uncached input is the remainder after the cached subset. `thoughtsTokenCount`
 * (reasoning) is embedded within the candidates output. Returns null when no
 * `usageMetadata` is present (never fabricates tokens).
 */
export function extractGeminiUsage(result: unknown, model: string): AttemptObservation | null {
  if (typeof result !== "object" || result === null) {
    return null;
  }
  const obj = result as Record<string, unknown>;
  const meta = obj["usageMetadata"];
  if (typeof meta !== "object" || meta === null) {
    return null;
  }
  const m = meta as Record<string, unknown>;
  const totalInput = usageInt(m["promptTokenCount"]);
  const cacheRead = Math.min(usageInt(m["cachedContentTokenCount"]), totalInput);
  // Gemini counts thinking tokens (`thoughtsTokenCount`) SEPARATELY from the visible
  // `candidatesTokenCount`, but both are billed as output. So total output is their sum,
  // with reasoning embedded within it — satisfying the `output >= reasoning` invariant.
  const reasoning = usageInt(m["thoughtsTokenCount"]);
  const output = usageInt(m["candidatesTokenCount"]) + reasoning;
  return {
    provider: "google",
    model: model || strProp(obj, "modelVersion"),
    tokens: tokenVector({
      inputUncached: totalInput - cacheRead,
      cacheRead,
      cacheWrite5m: 0,
      cacheWrite1h: 0,
      output,
      reasoning,
    }),
    isStreaming: false,
    partialRecovered: false,
  };
}

/** Pull terminal usage off a non-streaming OpenAI/Anthropic/Gemini response object. */
export function extractNonStreaming(
  result: unknown,
  model: string,
  provider: Provider,
): AttemptObservation | null {
  if (provider === "google") {
    return extractGeminiUsage(result, model);
  }
  if (typeof result !== "object" || result === null) {
    return null;
  }
  const obj = result as Record<string, unknown>;
  const usage = obj["usage"];
  if (typeof usage !== "object" || usage === null) {
    return null;
  }

  if (provider === "anthropic") {
    const acc = new AnthropicStreamAccumulator();
    acc.observe({ type: "message_start", message: { usage } });
    return acc.finalizeObservationNonStreaming({
      provider,
      model: model || strProp(obj, "model"),
    });
  }
  const acc = new OpenAIStreamAccumulator({ includeUsage: true });
  acc.observe({ usage });
  return acc.finalizeObservationNonStreaming({
    provider,
    model: model || strProp(obj, "model"),
  });
}
