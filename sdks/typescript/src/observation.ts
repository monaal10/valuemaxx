import type { TokenVector } from "./tokens.js";

/**
 * What an extractor pulls off one transport response/stream: usage + identity.
 *
 * Provider-specific response parsing (openai/anthropic, streaming) builds this;
 * the emit path stays provider-agnostic. Mirrors the Python
 * `valuemaxx.capture.patch.AttemptObservation`.
 */
export interface AttemptObservation {
  readonly provider: string;
  readonly model: string;
  readonly tokens: TokenVector;
  readonly isStreaming: boolean;
  /** Usage was only partially recovered (cancelled / missing include_usage). */
  readonly partialRecovered: boolean;
}
