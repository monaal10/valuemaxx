/**
 * Streaming terminal-value capture (the 2x fix, §5.2).
 *
 * Streaming usage is reported incrementally, but cost must be priced from the
 * **terminal** values, never the running deltas. Two provider accumulators
 * encode the exact rules (mirroring the Python `valuemaxx.capture.terminal`):
 *
 * **Anthropic** ({@link AnthropicStreamAccumulator}):
 *   - `output` is taken from `message_delta.usage.output_tokens` as the
 *     *cumulative terminal* value — each delta OVERWRITES, we never sum them;
 *   - cache tokens are read from `message_start` exactly ONCE — summing the
 *     cache fields that appear in both `message_start` and `message_delta` is
 *     the `@langchain/anthropic` 2x cache double-count bug, which this avoids;
 *   - the 5m/1h cache-write split comes from the nested
 *     `cache_creation.{ephemeral_5m,ephemeral_1h}_input_tokens` fields;
 *   - `reasoning` is DERIVED by counting `thinking` content blocks.
 *
 * **OpenAI** ({@link OpenAIStreamAccumulator}):
 *   - usage lives in the FINAL chunk only and REQUIRES `stream_options.include_usage`;
 *   - if usage never arrives (include_usage off, or a cancelled stream), we flag
 *     `partialRecovered` rather than logging a silent zero.
 *
 * A cancelled stream recovers whatever terminal value it has and flags
 * `partialRecovered` — never a silent zero (§5.2).
 */

import type { AttemptObservation } from "./observation.js";
import { tokenVector, type TokenVector } from "./tokens.js";

/** Narrow an untyped event payload to a string-keyed record (or empty). */
function asRecord(value: unknown): Record<string, unknown> {
  if (typeof value === "object" && value !== null && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return {};
}

/** Coerce a usage field to a non-negative int (a missing/None field is 0). */
function asInt(value: unknown): number {
  // guard: booleans are not usage counts even though `typeof true === "boolean"`.
  if (typeof value === "number" && Number.isFinite(value)) {
    const truncated = Math.trunc(value);
    return truncated > 0 ? truncated : 0;
  }
  return 0;
}

/** Accumulate an Anthropic streaming response to TERMINAL token values (§5.2). */
export class AnthropicStreamAccumulator {
  private cacheRead = 0;
  private cacheWrite5m = 0;
  private cacheWrite1h = 0;
  private inputUncached = 0;
  private outputTerminal = 0;
  private thinkingBlocks = 0;
  private sawMessageStart = false;
  private cancelled = false;

  /** Fold one streaming event into the accumulator (idempotent on cache fields). */
  observe(event: Record<string, unknown>): void {
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

  private observeMessageStart(event: Record<string, unknown>): void {
    // cache tokens are read here ONCE; later events never re-add them (the 2x fix).
    this.sawMessageStart = true;
    const usage = asRecord(asRecord(event["message"])["usage"]);
    this.inputUncached = asInt(usage["input_tokens"]);
    this.cacheRead = asInt(usage["cache_read_input_tokens"]);
    const cacheCreation = asRecord(usage["cache_creation"]);
    this.cacheWrite5m = asInt(cacheCreation["ephemeral_5m_input_tokens"]);
    this.cacheWrite1h = asInt(cacheCreation["ephemeral_1h_input_tokens"]);
    // message_start may already carry an output_tokens; treat it as the first terminal.
    this.outputTerminal = asInt(usage["output_tokens"]);
  }

  private observeMessageDelta(event: Record<string, unknown>): void {
    // output_tokens here is the CUMULATIVE terminal value — OVERWRITE, never sum.
    const usage = asRecord(event["usage"]);
    if ("output_tokens" in usage) {
      this.outputTerminal = asInt(usage["output_tokens"]);
    }
  }

  /** Record that the stream was cancelled before its terminal message_stop. */
  markCancelled(): void {
    this.cancelled = true;
  }

  /** Build the terminal {@link TokenVector} (output >= reasoning by construction). */
  finalize(): TokenVector {
    // reasoning is embedded within output; ensure output covers the derived count.
    const output = Math.max(this.outputTerminal, this.thinkingBlocks);
    return tokenVector({
      inputUncached: this.inputUncached,
      cacheRead: this.cacheRead,
      cacheWrite5m: this.cacheWrite5m,
      cacheWrite1h: this.cacheWrite1h,
      output,
      reasoning: this.thinkingBlocks,
    });
  }

  /** Build the {@link AttemptObservation} for the emit path. */
  finalizeObservation(args: { provider: string; model: string }): AttemptObservation {
    const partial = this.cancelled || !this.sawMessageStart;
    return {
      provider: args.provider,
      model: args.model,
      tokens: this.finalize(),
      isStreaming: true,
      partialRecovered: partial,
    };
  }

  /**
   * Build the observation for a NON-streaming response (full terminal usage in
   * one object): `isStreaming` and `partialRecovered` are both false.
   */
  finalizeObservationNonStreaming(args: {
    provider: string;
    model: string;
  }): AttemptObservation {
    return {
      provider: args.provider,
      model: args.model,
      tokens: this.finalize(),
      isStreaming: false,
      partialRecovered: false,
    };
  }
}

/**
 * Accumulate an OpenAI streaming response; usage is in the FINAL chunk only (§5.2).
 *
 * `includeUsage` records whether `stream_options.include_usage` was set. When
 * false, usage never arrives and the stream is flagged `partialRecovered`
 * rather than reporting a silent zero.
 */
export class OpenAIStreamAccumulator {
  private inputTotal = 0;
  private cacheReadRaw = 0;
  private output = 0;
  private sawUsage = false;
  private cancelled = false;
  private readonly includeUsage: boolean;

  constructor(args: { includeUsage: boolean }) {
    this.includeUsage = args.includeUsage;
  }

  /** Fold one streaming chunk; only the final chunk carries usage. */
  observe(chunk: Record<string, unknown>): void {
    const usage = chunk["usage"];
    if (typeof usage !== "object" || usage === null || Array.isArray(usage)) {
      return;
    }
    const usageMap = usage as Record<string, unknown>;
    this.sawUsage = true;
    this.inputTotal = asInt(usageMap["prompt_tokens"]);
    const details = asRecord(usageMap["prompt_tokens_details"]);
    this.cacheReadRaw = asInt(details["cached_tokens"]);
    this.output = asInt(usageMap["completion_tokens"]);
  }

  /** Record that the stream was cancelled before the final usage chunk. */
  markCancelled(): void {
    this.cancelled = true;
  }

  /** Build the terminal {@link TokenVector} (uncached = prompt - cached). */
  finalize(): TokenVector {
    // OpenAI has no distinct cache-write class; uncached input is the remainder.
    const cacheRead = Math.min(this.cacheReadRaw, this.inputTotal);
    return tokenVector({
      inputUncached: this.inputTotal - cacheRead,
      cacheRead,
      cacheWrite5m: 0,
      cacheWrite1h: 0,
      output: this.output,
      reasoning: 0,
    });
  }

  /** Build the {@link AttemptObservation}; flag partial if usage never arrived. */
  finalizeObservation(args: { provider: string; model: string }): AttemptObservation {
    // includeUsage off means usage will never arrive: a missing-usage outcome
    // even if the stream completed cleanly, so the flag reflects sawUsage too.
    const partial = this.cancelled || !this.sawUsage || !this.includeUsage;
    return {
      provider: args.provider,
      model: args.model,
      tokens: this.finalize(),
      isStreaming: true,
      partialRecovered: partial,
    };
  }

  /**
   * Build the observation for a NON-streaming response (usage present on the
   * single response object): `isStreaming` and `partialRecovered` are false.
   */
  finalizeObservationNonStreaming(args: {
    provider: string;
    model: string;
  }): AttemptObservation {
    return {
      provider: args.provider,
      model: args.model,
      tokens: this.finalize(),
      isStreaming: false,
      partialRecovered: false,
    };
  }
}
