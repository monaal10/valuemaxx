/**
 * Streaming terminal-value capture (the 2x fix, §5.2).
 *
 * Mirrors the Python `packages/capture/tests/test_terminal.py`:
 *   - Anthropic output is TERMINAL (overwrite, never sum the deltas);
 *   - Anthropic cache tokens come from `message_start` ONCE (no 2x double-count);
 *   - the 5m/1h split comes from nested `cache_creation` fields;
 *   - reasoning is the count of `thinking` content blocks (embedded in output);
 *   - OpenAI usage is in the FINAL chunk only and requires `include_usage`;
 *     absent -> the stream is flagged `partialRecovered`, never a silent zero.
 */

import { describe, expect, it } from "vitest";

import { AnthropicStreamAccumulator, OpenAIStreamAccumulator } from "../src/terminal.js";

function anthropicMessageStart(args: {
  inputTokens: number;
  cacheRead: number;
  cache5m: number;
  cache1h: number;
  outputTokens?: number;
}): Record<string, unknown> {
  return {
    type: "message_start",
    message: {
      usage: {
        input_tokens: args.inputTokens,
        cache_read_input_tokens: args.cacheRead,
        cache_creation_input_tokens: args.cache5m + args.cache1h,
        cache_creation: {
          ephemeral_5m_input_tokens: args.cache5m,
          ephemeral_1h_input_tokens: args.cache1h,
        },
        output_tokens: args.outputTokens ?? 0,
      },
    },
  };
}

function anthropicMessageDelta(outputTokens: number): Record<string, unknown> {
  // message_delta.usage.output_tokens is the CUMULATIVE terminal value.
  return { type: "message_delta", usage: { output_tokens: outputTokens } };
}

function thinkingBlockStart(): Record<string, unknown> {
  return { type: "content_block_start", content_block: { type: "thinking" } };
}

describe("AnthropicStreamAccumulator", () => {
  it("takes output TERMINALLY, not summed: 60, not 35+60=95", () => {
    const acc = new AnthropicStreamAccumulator();
    acc.observe(anthropicMessageStart({ inputTokens: 100, cacheRead: 0, cache5m: 0, cache1h: 0 }));
    acc.observe(anthropicMessageDelta(35)); // intermediate cumulative
    acc.observe(anthropicMessageDelta(60)); // final cumulative (terminal)
    expect(acc.finalize().output).toBe(60); // the terminal value, NOT 35 + 60
  });

  it("reads cache from message_start ONCE, never doubled (@langchain 2x bug fix)", () => {
    const acc = new AnthropicStreamAccumulator();
    acc.observe(
      anthropicMessageStart({ inputTokens: 10, cacheRead: 200, cache5m: 50, cache1h: 30 }),
    );
    // a later event repeating cache fields must NOT be re-added.
    acc.observe(anthropicMessageDelta(5));
    const tokens = acc.finalize();
    expect(tokens.cacheRead).toBe(200); // taken once, not doubled
    expect(tokens.cacheWrite5m).toBe(50);
    expect(tokens.cacheWrite1h).toBe(30);
  });

  it("splits 5m/1h from the nested cache_creation fields", () => {
    const acc = new AnthropicStreamAccumulator();
    acc.observe(anthropicMessageStart({ inputTokens: 10, cacheRead: 0, cache5m: 12, cache1h: 34 }));
    acc.observe(anthropicMessageDelta(1));
    const tokens = acc.finalize();
    expect(tokens.cacheWrite5m).toBe(12);
    expect(tokens.cacheWrite1h).toBe(34);
  });

  it("derives reasoning from thinking-block count, embedded within output", () => {
    const acc = new AnthropicStreamAccumulator();
    acc.observe(anthropicMessageStart({ inputTokens: 10, cacheRead: 0, cache5m: 0, cache1h: 0 }));
    acc.observe(thinkingBlockStart());
    acc.observe(thinkingBlockStart());
    acc.observe(anthropicMessageDelta(50));
    const tokens = acc.finalize();
    expect(tokens.reasoning).toBe(2);
    expect(tokens.output).toBeGreaterThanOrEqual(tokens.reasoning); // reasoning ⊆ output
  });

  it("flags is_streaming and not partial on a clean stream", () => {
    const acc = new AnthropicStreamAccumulator();
    acc.observe(anthropicMessageStart({ inputTokens: 10, cacheRead: 0, cache5m: 0, cache1h: 0 }));
    acc.observe(anthropicMessageDelta(5));
    const obs = acc.finalizeObservation({ provider: "anthropic", model: "claude-opus-4-8" });
    expect(obs.isStreaming).toBe(true);
    expect(obs.partialRecovered).toBe(false);
  });

  it("recovers the partial terminal value on a cancelled stream, then flags it", () => {
    const acc = new AnthropicStreamAccumulator();
    acc.observe(anthropicMessageStart({ inputTokens: 100, cacheRead: 0, cache5m: 0, cache1h: 0 }));
    acc.observe(anthropicMessageDelta(20));
    acc.markCancelled(); // cut off before message_stop
    const obs = acc.finalizeObservation({ provider: "anthropic", model: "claude-opus-4-8" });
    expect(obs.partialRecovered).toBe(true); // flagged, never silently zero
    expect(obs.tokens.output).toBe(20); // recovered the partial terminal value
  });
});

function openaiUsageChunk(args: {
  prompt: number;
  cached: number;
  completion: number;
}): Record<string, unknown> {
  // OpenAI sends usage only in the FINAL chunk, and only with include_usage.
  return {
    usage: {
      prompt_tokens: args.prompt,
      completion_tokens: args.completion,
      prompt_tokens_details: { cached_tokens: args.cached },
    },
  };
}

function openaiContentChunk(): Record<string, unknown> {
  return { choices: [{ delta: { content: "hi" } }], usage: null };
}

describe("OpenAIStreamAccumulator", () => {
  it("takes usage from the final chunk only; uncached = prompt - cached", () => {
    const acc = new OpenAIStreamAccumulator({ includeUsage: true });
    acc.observe(openaiContentChunk());
    acc.observe(openaiContentChunk());
    acc.observe(openaiUsageChunk({ prompt: 100, cached: 40, completion: 25 }));
    const tokens = acc.finalize();
    expect(tokens.inputUncached).toBe(60); // 100 prompt - 40 cached
    expect(tokens.cacheRead).toBe(40); // cache tokens not doubled into input
    expect(tokens.output).toBe(25);
  });

  it("flags partial when include_usage is off (no usage ever arrives), never zero", () => {
    const acc = new OpenAIStreamAccumulator({ includeUsage: false });
    acc.observe(openaiContentChunk());
    acc.observe(openaiContentChunk()); // no usage chunk ever arrives
    const obs = acc.finalizeObservation({ provider: "openai", model: "gpt-5" });
    expect(obs.partialRecovered).toBe(true);
    expect(obs.isStreaming).toBe(true);
  });

  it("flags partial when cancelled before the final usage chunk", () => {
    const acc = new OpenAIStreamAccumulator({ includeUsage: true });
    acc.observe(openaiContentChunk());
    acc.markCancelled();
    const obs = acc.finalizeObservation({ provider: "openai", model: "gpt-5" });
    expect(obs.partialRecovered).toBe(true);
  });
});
