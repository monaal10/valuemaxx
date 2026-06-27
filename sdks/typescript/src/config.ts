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
    endpoint: config.endpoint,
    captureContent: config.captureContent ?? false,
    serviceName: config.serviceName ?? "valuemaxx",
    ingestKey: new SecretString(config.ingestKey),
  };
}
