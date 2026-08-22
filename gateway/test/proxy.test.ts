import { afterEach, describe, expect, it, vi } from "vitest";

import gateway from "../src/index.js";
import { configIdentity } from "../src/config.js";

const realFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = realFetch;
});

describe("proxy fail-open body handling", () => {
  it("retries with the untouched original body after the capture path consumed it", async () => {
    const original = JSON.stringify({
      model: "gpt-5",
      messages: [{ role: "user", content: "keep me byte-for-byte" }],
    });
    const bodies: string[] = [];
    const fetchMock = vi.fn(async (request: Request) => {
      bodies.push(await request.text());
      if (bodies.length === 1) throw new Error("capture-path failure");
      return new Response("ok", { status: 200 });
    });
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const response = await gateway.fetch(
      new Request("https://gateway.test/openai/v1/chat/completions", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: original,
      }),
      { VALUEMAXX_BACKEND: "https://backend.test" },
      { waitUntil: () => undefined } as unknown as ExecutionContext,
    );

    expect(await response.text()).toBe("ok");
    expect(bodies).toEqual([original, original]);
  });

  it("keeps observe-only traffic byte-identical and strips the bypass header", async () => {
    const original = '{"messages":[], "model":"gpt-5"}';
    let forwarded: Request | undefined;
    globalThis.fetch = (async (request: Request) => {
      forwarded = request;
      return new Response("ok", { status: 200 });
    }) as typeof fetch;

    await gateway.fetch(
      new Request("https://gateway.test/openai/v1/chat/completions", {
        method: "POST",
        headers: { "content-type": "application/json", "x-vmx-bypass": "1" },
        body: original,
      }),
      {
        VALUEMAXX_BACKEND: "https://backend.test",
        VALUEMAXX_ENFORCEMENT_ENABLED: "true",
        VALUEMAXX_DEPLOYMENT_POLICY: "malformed",
      },
      { waitUntil: () => undefined } as unknown as ExecutionContext,
    );

    expect(await forwarded?.text()).toBe(original);
    expect(forwarded?.headers.get("x-vmx-bypass")).toBeNull();
  });

  it("applies a source-matched call-site deployment when explicitly enabled", async () => {
    const original = JSON.stringify({ model: "gpt-5", messages: [] });
    const source = await configIdentity("openai", original);
    let forwardedBody = "";
    globalThis.fetch = (async (request: Request) => {
      forwardedBody = await request.text();
      return new Response("ok", { status: 200 });
    }) as typeof fetch;

    await gateway.fetch(
      new Request("https://gateway.test/openai/v1/chat/completions", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-vmx-call-site": "checkout.classify",
          "x-vmx-run-id": "run-1",
        },
        body: original,
      }),
      {
        VALUEMAXX_BACKEND: "https://backend.test",
        VALUEMAXX_ENFORCEMENT_ENABLED: "true",
        VALUEMAXX_DEPLOYMENT_POLICY: JSON.stringify({
          id: "dep-1",
          provider: "openai",
          callSiteId: "checkout.classify",
          sourceConfigId: source?.configId,
          rolloutPercent: 100,
          patch: { model: "gpt-5-mini", reasoningEffort: "low", maxTokens: 100 },
        }),
      },
      { waitUntil: () => undefined } as unknown as ExecutionContext,
    );

    expect(JSON.parse(forwardedBody)).toMatchObject({
      model: "gpt-5-mini",
      reasoning_effort: "low",
      max_tokens: 100,
      messages: [],
    });
  });

  it("reports a failed response with no usage as a zero-token attempt", async () => {
    let reported: { attributes?: Record<string, unknown> } = {};
    const pending: Promise<unknown>[] = [];
    globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      if (input instanceof Request) {
        return new Response("rate limited", {
          status: 429,
          headers: { "content-type": "text/plain" },
        });
      }
      reported = JSON.parse(String(init?.body)) as typeof reported;
      return new Response("ok");
    }) as typeof fetch;

    const response = await gateway.fetch(
      new Request("https://gateway.test/openai/v1/chat/completions", {
        method: "POST",
        headers: { "content-type": "application/json", "x-vmx-key": "key" },
        body: JSON.stringify({ model: "gpt-5", messages: [] }),
      }),
      { VALUEMAXX_BACKEND: "https://backend.test" },
      { waitUntil: (promise: Promise<unknown>) => pending.push(promise) } as unknown as ExecutionContext,
    );
    await Promise.all(pending);

    expect(response.status).toBe(429);
    expect(reported.attributes).toMatchObject({
      "ai_margin.http_status": 429,
      "gen_ai.usage.input_tokens": 0,
      "gen_ai.usage.output_tokens": 0,
      "ai_margin.partial_recovered": true,
    });
  });
});
