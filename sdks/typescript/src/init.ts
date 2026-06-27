/**
 * `init()` — the one-line, fail-open SDK entrypoint (§5.1, H9).
 *
 * `init()` installs real OTel instrumentation: it builds an OTLP/HTTP exporter
 * pointed at the configured ingest endpoint (authenticated with the tenant
 * ingest key), registers a tracer provider, runs the startup self-test, and —
 * when client instances are injected — wraps their `create` methods to capture
 * model/usage/cost off the hot path. For the Vercel AI SDK the returned
 * {@link InitResult.tracer} is what the host passes to `experimental_telemetry`.
 *
 * Only the config validation may throw (a bad literal at the call site, as
 * intended); every instrumentation step thereafter runs inside a fail-open
 * guard, so an internal error is logged + surfaced as a warning and NEVER
 * propagates into the host. Content (prompt/response) is OFF by default (§9.1);
 * the ingest key is held in a {@link SecretString} that never reaches a log.
 */

import { randomUUID } from "node:crypto";

import type { Tracer } from "@opentelemetry/api";
import { OTLPTraceExporter } from "@opentelemetry/exporter-trace-otlp-http";
import { resourceFromAttributes } from "@opentelemetry/resources";
import {
  BasicTracerProvider,
  BatchSpanProcessor,
  SimpleSpanProcessor,
  type SpanExporter,
  type SpanProcessor,
} from "@opentelemetry/sdk-trace-base";

import { type EffectiveConfig, type InitConfig, resolveConfig } from "./config.js";
import {
  type InstrumentDeps,
  type InstrumentHandle,
  instrumentMethod,
  type Provider,
} from "./instrumentation.js";
import { type CaptureGranularity, versionSelftest } from "./selftest.js";

/** The non-secret config echo surfaced on the {@link InitResult}. */
export interface EffectiveConfigEcho {
  readonly tenantId: string;
  readonly endpoint: string;
  readonly captureContent: boolean;
  readonly serviceName: string;
}

/** The outcome of {@link init}: what was wired, the effective config, warnings. */
export interface InitResult {
  /** True if at least one client was instrumented. */
  readonly capturePatched: boolean;
  /** The effective capture granularity (degraded to per_call on a self-test warning). */
  readonly captureGranularity: CaptureGranularity;
  /** Loud, non-silent warnings from the self-test + wiring (never thrown). */
  readonly warnings: readonly string[];
  /** The non-secret config echo (never carries the ingest key). */
  readonly effective: EffectiveConfigEcho;
  /**
   * The tracer to hand to the Vercel AI SDK via `experimental_telemetry`, e.g.
   * `streamText({ experimental_telemetry: { isEnabled: true, tracer } })`.
   * `undefined` only if the exporter/provider failed to start (fail-open).
   */
  readonly tracer: Tracer | undefined;
  /** Reversible handles for every instrumented client method. */
  readonly handles: readonly InstrumentHandle[];
  /** Force-flush pending spans to the exporter (off-path; useful in tests). */
  forceFlush(): Promise<void>;
  /** Flush + shut down the exporter/provider (drains pending spans). */
  shutdown(): Promise<void>;
}

/** A client instance to instrument, plus which provider family it is. */
export interface ClientTarget {
  readonly client: unknown;
  readonly provider: Provider;
}

/** Extended init options: the literal config plus injectable test seams. */
export interface InitOptions extends InitConfig {
  /** OpenAI/Anthropic client instances to wrap (instance-scoped, reversible). */
  readonly clients?: readonly ClientTarget[];
  /** Inject the span exporter (tests pass an in-memory exporter). */
  readonly exporter?: SpanExporter;
  /** Inject the id generator (tests pass a deterministic counter). */
  readonly newId?: () => string;
}

/** The `create`-method locations we wrap per provider family. */
const METHOD_PATHS: Readonly<Record<Provider, readonly string[]>> = {
  openai: ["chat.completions", "responses"],
  anthropic: ["messages"],
};

/** Resolve a dotted path (e.g. "chat.completions") to its owner object. */
function resolveOwner(client: unknown, path: string): Record<string, unknown> | null {
  let current: unknown = client;
  for (const segment of path.split(".")) {
    if (typeof current !== "object" || current === null) {
      return null;
    }
    current = (current as Record<string, unknown>)[segment];
  }
  if (typeof current !== "object" || current === null) {
    return null;
  }
  return current as Record<string, unknown>;
}

/**
 * Instrument cost capture in one call. Never raises into the host (fail-open, H9).
 *
 * The config args are validated first (a bad literal raises at the call site, as
 * intended); every instrumentation step thereafter is fail-open. When `clients`
 * are provided their `create` methods are wrapped (instance-scoped) and the
 * returned `handles` let the caller uninstrument; otherwise `init` stands up the
 * tracer + exporter only (e.g. for the Vercel AI SDK tracer-injection path).
 */
export function init(options: InitOptions): InitResult {
  // config validation — the ONLY part allowed to throw (a call-site programming error).
  const config: EffectiveConfig = resolveConfig(options);
  const logger = options.logger ?? console;

  const effective: EffectiveConfigEcho = {
    tenantId: config.tenantId,
    endpoint: config.endpoint,
    captureContent: config.captureContent,
    serviceName: config.serviceName,
  };

  const warnings: string[] = [];
  let granularity: CaptureGranularity = "per_attempt";
  let tracer: Tracer | undefined;
  let provider: BasicTracerProvider | undefined;
  const handles: InstrumentHandle[] = [];
  const newId = options.newId ?? ((): string => randomUUID());

  // everything below is fail-open: an internal error is logged + warned, never raised.
  try {
    const clients = options.clients ?? [];
    const selftest = versionSelftest({
      installedVersions: options.installedVersions ?? {},
      hookPresent: options.hookPresent ?? clients.length > 0,
      logger,
    });
    warnings.push(...selftest.warnings);
    granularity = selftest.granularity;

    const injectedExporter = options.exporter;
    const exporter: SpanExporter =
      injectedExporter ??
      new OTLPTraceExporter({
        url: config.endpoint,
        headers: {
          "x-valuemaxx-ingest-key": config.ingestKey.reveal(),
          "x-valuemaxx-tenant-id": config.tenantId,
        },
      });
    // An injected exporter (test path) flushes synchronously via SimpleSpanProcessor;
    // production batches off-path so the host call path stays non-blocking (H9).
    const processor: SpanProcessor =
      injectedExporter !== undefined
        ? new SimpleSpanProcessor(exporter)
        : new BatchSpanProcessor(exporter);
    provider = new BasicTracerProvider({
      resource: resourceFromAttributes({ "service.name": config.serviceName }),
      spanProcessors: [processor],
    });
    tracer = provider.getTracer("valuemaxx");

    const deps: InstrumentDeps = {
      tracer,
      tenantId: config.tenantId,
      granularity,
      newId,
      logger,
    };

    for (const target of clients) {
      for (const path of METHOD_PATHS[target.provider]) {
        const owner = resolveOwner(target.client, path);
        if (owner === null || typeof owner["create"] !== "function") {
          continue; // this client shape doesn't expose this method — skip, don't fail.
        }
        try {
          handles.push(
            instrumentMethod({ owner, method: "create", provider: target.provider }, deps),
          );
        } catch (err: unknown) {
          warnings.push(
            `valuemaxx: could not instrument ${target.provider}.${path} (${String(err)})`,
          );
        }
      }
    }
  } catch (err: unknown) {
    const msg = `valuemaxx init suppressed an internal error (fail-open): ${String(err)}`;
    warnings.push(msg);
    logger.warn(msg);
  }

  const capturedProvider = provider;
  return {
    capturePatched: handles.length > 0,
    captureGranularity: granularity,
    warnings,
    effective,
    tracer,
    handles,
    async forceFlush(): Promise<void> {
      try {
        if (capturedProvider !== undefined) {
          await capturedProvider.forceFlush();
        }
      } catch (err: unknown) {
        logger.warn("valuemaxx: suppressed a flush error (fail-open)", err);
      }
    },
    async shutdown(): Promise<void> {
      try {
        for (const handle of handles) {
          handle.uninstrument();
        }
        if (capturedProvider !== undefined) {
          await capturedProvider.shutdown();
        }
      } catch (err: unknown) {
        logger.warn("valuemaxx: suppressed a shutdown error (fail-open)", err);
      }
    },
  };
}
