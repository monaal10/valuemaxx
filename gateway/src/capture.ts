/**
 * Turning a provider HTTP exchange into an `AttemptObservation`.
 *
 * The SDK extracted usage from a response object it was handed by a client library.
 * A gateway sees bytes instead, so it must parse them — but the *arithmetic* and the
 * accumulator state machines are the same, and those encode real bugs already fixed
 * (Anthropic's `message_delta.usage.output_tokens` overwrites rather than sums; cache
 * tokens are read once from `message_start`). Reusing them verbatim is the point:
 * a second implementation would re-earn those bugs.
 *
 * Two shapes to handle:
 *
 * - **Non-streaming** — one JSON body, read after the response is fully proxied.
 * - **Streaming (SSE)** — `data: {...}` frames folded into an accumulator as they
 *   pass through. A client that disconnects mid-stream still yields an observation,
 *   flagged `partialRecovered`, rather than nothing at all.
 */

import type { AttemptObservation } from "../../sdks/typescript/src/observation.js";
import {
  AnthropicStreamAccumulator,
  GeminiStreamAccumulator,
  OpenAIStreamAccumulator,
} from "../../sdks/typescript/src/terminal.js";

export type Provider = "openai" | "anthropic" | "gemini" | "openrouter";

/** A provider's streaming accumulator, behind the one shape the gateway needs. */
export interface StreamAccumulator {
  observe(event: Record<string, unknown>): void;
  markCancelled(): void;
  finalizeObservation(args: {
    provider: string;
    model: string;
  }): AttemptObservation;
}

export function newAccumulator(
  provider: Provider,
  opts: { includeUsage?: boolean } = {},
): StreamAccumulator {
  switch (provider) {
    case "anthropic":
      return new AnthropicStreamAccumulator();
    case "gemini":
      return new GeminiStreamAccumulator();
    // OpenRouter speaks the OpenAI wire shape, so it accumulates identically. Its
    // authoritative `usage.cost` is read separately (see `readInlineCost`).
    case "openai":
    case "openrouter":
      // OpenAI streams usage ONLY when the caller set `stream_options.include_usage`.
      // The gateway can see that in the request body, so it tells the accumulator —
      // which then flags `partialRecovered` instead of reporting a silent zero for a
      // stream that was never going to carry usage in the first place.
      return new OpenAIStreamAccumulator({
        includeUsage: opts.includeUsage ?? false,
      });
  }
}

/** Did the caller ask OpenAI to include usage in the stream? */
export function requestedStreamUsage(requestBody: string | undefined): boolean {
  if (!requestBody) return false;
  try {
    const parsed: unknown = JSON.parse(requestBody);
    if (!parsed || typeof parsed !== "object") return false;
    const opts = (parsed as Record<string, unknown>)["stream_options"];
    return Boolean(asRecord(opts)?.["include_usage"]);
  } catch {
    return false;
  }
}

/**
 * Fold one SSE chunk into `acc`, returning the leftover partial line.
 *
 * SSE frames are newline-delimited but a chunk may split one mid-line, so the caller
 * threads the remainder back in. `[DONE]` is OpenAI's terminator and is not JSON;
 * a frame that fails to parse is skipped rather than throwing — a malformed frame
 * must cost us a token count, never the user's response.
 */
export function foldSseChunk(
  acc: StreamAccumulator,
  chunk: string,
  carry: string,
): string {
  const buffer = carry + chunk;
  const lines = buffer.split("\n");
  // The final element is either "" (chunk ended on a newline) or a partial line.
  const remainder = lines.pop() ?? "";
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed.startsWith("data:")) continue;
    const payload = trimmed.slice(5).trim();
    if (!payload || payload === "[DONE]") continue;
    try {
      const parsed: unknown = JSON.parse(payload);
      if (parsed && typeof parsed === "object") {
        acc.observe(parsed as Record<string, unknown>);
      }
    } catch {
      // A frame we cannot parse is a frame we cannot count. Never fatal.
    }
  }
  return remainder;
}

/**
 * Fold a complete non-streaming JSON body into an accumulator-equivalent observation.
 *
 * The accumulators are event-driven, and a non-streaming body is not an event — so
 * this maps the terminal usage block directly. Shapes differ per provider, which is
 * exactly the per-provider knowledge a proxy cannot avoid owning.
 */
export function observeNonStreaming(
  provider: Provider,
  body: Record<string, unknown>,
  fallbackModel: string,
): AttemptObservation | undefined {
  const model = asString(body["model"]) || fallbackModel;
  const usage = asRecord(body["usage"]) ?? asRecord(body["usageMetadata"]);
  if (!usage) return undefined;

  if (provider === "anthropic") {
    const cacheCreation = asRecord(usage["cache_creation"]);
    return {
      provider,
      model,
      tokens: {
        inputUncached: asInt(usage["input_tokens"]),
        cacheRead: asInt(usage["cache_read_input_tokens"]),
        cacheWrite5m: asInt(cacheCreation?.["ephemeral_5m_input_tokens"]),
        cacheWrite1h: asInt(cacheCreation?.["ephemeral_1h_input_tokens"]),
        output: asInt(usage["output_tokens"]),
        reasoning: 0,
      },
      isStreaming: false,
      partialRecovered: false,
    };
  }

  if (provider === "gemini") {
    // Gemini reports a TOTAL prompt count; cached content is a subset of it, so the
    // uncached remainder is the difference. Adding them would double-count input.
    const cached = asInt(usage["cachedContentTokenCount"]);
    const prompt = asInt(usage["promptTokenCount"]);
    return {
      provider,
      model,
      tokens: {
        inputUncached: Math.max(0, prompt - cached),
        cacheRead: cached,
        cacheWrite5m: 0,
        cacheWrite1h: 0,
        output: asInt(usage["candidatesTokenCount"]),
        reasoning: asInt(usage["thoughtsTokenCount"]),
      },
      isStreaming: false,
      partialRecovered: false,
    };
  }

  // OpenAI / OpenRouter: `prompt_tokens` INCLUDES cached, same subset rule.
  const details = asRecord(usage["prompt_tokens_details"]);
  const cachedIn = asInt(details?.["cached_tokens"]);
  const promptIn = asInt(usage["prompt_tokens"]);
  const outDetails = asRecord(usage["completion_tokens_details"]);
  return {
    provider,
    model,
    tokens: {
      inputUncached: Math.max(0, promptIn - cachedIn),
      cacheRead: cachedIn,
      cacheWrite5m: 0,
      cacheWrite1h: 0,
      output: asInt(usage["completion_tokens"]),
      reasoning: asInt(outDetails?.["reasoning_tokens"]),
    },
    isStreaming: false,
    partialRecovered: false,
  };
}

/**
 * OpenRouter's authoritative billed cost, when present.
 *
 * This is the one provider that tells us what it actually charged, so the resulting
 * event is `provider_reconciled` rather than an estimate off a price card. An
 * explicitly-flagged estimate (`usage.is_estimate`) is refused: a labeled guess must
 * not be laundered into the reconciled tier.
 */
export function readInlineCost(
  body: Record<string, unknown>,
): number | undefined {
  const usage = asRecord(body["usage"]);
  if (!usage || usage["is_estimate"] === true) return undefined;
  const cost = usage["cost"];
  return typeof cost === "number" && Number.isFinite(cost) ? cost : undefined;
}

function asRecord(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined;
}

function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function asInt(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value)
    ? Math.trunc(value)
    : 0;
}
