/**
 * The SDK's init config + effective-config echo (strict, secret-safe).
 *
 * Mirrors the Python `valuemaxx.sdk.config`. `ingestKey` is held in a wrapper
 * whose `toString`/`toJSON` redact it, so it never appears in a log, a thrown
 * error, or a serialized config dump. `captureContent` is OFF by default — cost
 * capture needs only token counts + metadata (§9.1).
 */

/**
 * A secret string that never reveals itself in `toString`, `toJSON`, or
 * `util.inspect`. The raw value is only accessible via {@link reveal}.
 */
export class SecretString {
  readonly #value: string;

  constructor(value: string) {
    this.#value = value;
  }

  /** Reveal the raw secret. The ONLY way to read the underlying value. */
  reveal(): string {
    return this.#value;
  }

  toString(): string {
    return "SecretString(***)";
  }

  toJSON(): string {
    return "***";
  }

  /** Node's `util.inspect` hook — keeps the secret out of `console.log`/dumps. */
  [Symbol.for("nodejs.util.inspect.custom")](): string {
    return "SecretString(***)";
  }
}

/** User-supplied options for {@link import("./init.js").init}. */
export interface InitConfig {
  /** The tenant scope (required; rides every emitted span). */
  readonly tenantId: string;
  /** The per-tenant ingest key, sent as an OTLP auth header. Never logged. */
  readonly ingestKey: string;
  /** The OTLP/HTTP ingest endpoint (must be http(s)). */
  readonly endpoint: string;
  /** Capture prompt/response content. OFF by default (§9.1). */
  readonly captureContent?: boolean;
  /** The OTel service.name resource attribute. */
  readonly serviceName?: string;
  /** Installed SDK versions for the startup self-test (injectable for tests). */
  readonly installedVersions?: Readonly<Record<string, string>>;
  /** Hard-set whether the instrumentation hook took effect (injectable for tests). */
  readonly hookPresent?: boolean;
  /** A logger sink (defaults to `console`). */
  readonly logger?: Pick<Console, "warn" | "error"> | undefined;
}

/** The validated, secret-safe configuration. */
export interface EffectiveConfig {
  readonly tenantId: string;
  readonly endpoint: string;
  readonly captureContent: boolean;
  readonly serviceName: string;
  readonly ingestKey: SecretString;
}

/** Raised only by config validation — a programming error at the call site. */
export class InitConfigError extends Error {
  public override readonly name = "InitConfigError";
}

/**
 * Validate + normalize raw init options into an {@link EffectiveConfig}.
 *
 * This is the ONLY part of init allowed to throw (a bad literal at the call
 * site, surfaced loudly). Everything downstream of it is fail-open.
 */
export function resolveConfig(config: InitConfig): EffectiveConfig {
  if (typeof config.tenantId !== "string" || config.tenantId.length === 0) {
    throw new InitConfigError("tenantId is required and must be a non-empty string");
  }
  if (typeof config.ingestKey !== "string" || config.ingestKey.length === 0) {
    throw new InitConfigError("ingestKey is required and must be a non-empty string");
  }
  if (typeof config.endpoint !== "string") {
    throw new InitConfigError("endpoint is required and must be a string");
  }
  if (!config.endpoint.startsWith("http://") && !config.endpoint.startsWith("https://")) {
    throw new InitConfigError(`endpoint must be http(s), got ${JSON.stringify(config.endpoint)}`);
  }
  return {
    tenantId: config.tenantId,
    endpoint: normalizeTracesEndpoint(config.endpoint),
    captureContent: config.captureContent ?? false,
    serviceName: config.serviceName ?? "valuemaxx",
    ingestKey: new SecretString(config.ingestKey),
  };
}

/**
 * Resolve the OTLP traces URL the exporter actually POSTs to.
 *
 * The collector is mounted at `/v1/traces`. Following the OTel convention for
 * `OTEL_EXPORTER_OTLP_ENDPOINT`, a *base* endpoint (no path, or just `/`) gets
 * `/v1/traces` appended — so `http://127.0.0.1:8000` reaches the collector, not the
 * root. An endpoint that already carries a path (a signal-specific URL ending in
 * `/v1/traces`, or a deliberate custom gateway path) is used verbatim.
 */
function normalizeTracesEndpoint(endpoint: string): string {
  let url: URL;
  try {
    url = new URL(endpoint);
  } catch {
    // Not a parseable URL — leave it to the exporter (the http(s) prefix check passed);
    // never throw here for a non-literal config issue.
    return endpoint;
  }
  if (url.pathname === "" || url.pathname === "/") {
    url.pathname = "/v1/traces";
    // URL serializes a path-only base without a trailing slash question; toString is canonical.
    return url.toString();
  }
  return endpoint;
}
