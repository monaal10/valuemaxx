import { afterEach, describe, expect, it } from "vitest";

import type { AttemptObservation } from "../../sdks/typescript/src/observation.js";
import { readIntent } from "../src/headers.js";
import { reportSpan } from "../src/report.js";

const realFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = realFetch;
});

describe("gateway config stamping", () => {
  it("reports the actual served identity, call site, and HTTP status", async () => {
    let payload: { attributes?: Record<string, unknown> } = {};
    globalThis.fetch = (async (_input: RequestInfo | URL, init?: RequestInit) => {
      payload = JSON.parse(String(init?.body)) as typeof payload;
      return new Response("ok");
    }) as typeof fetch;
    const intent = readIntent(
      new Headers({
        "x-vmx-key": "key",
        "x-vmx-run-id": "run-1",
        "x-vmx-call-site": "checkout.classify",
      }),
      () => "minted",
    );
    const observation: AttemptObservation = {
      provider: "openai",
      model: "gpt-5-mini",
      tokens: {
        inputUncached: 10,
        cacheRead: 0,
        cacheWrite5m: 0,
        cacheWrite1h: 0,
        output: 2,
        reasoning: 0,
      },
      isStreaming: false,
      partialRecovered: false,
    };

    await reportSpan("https://backend.test", intent, observation, {
      status: 201,
      configIdentity: {
        systemHash: "system",
        toolsHash: "tools",
        paramsHash: "params",
        configId: "served-config",
      },
    });

    expect(payload.attributes).toMatchObject({
      "gen_ai.request.model": "gpt-5-mini",
      "ai_margin.call_site_id": "checkout.classify",
      "ai_margin.config.system_hash": "system",
      "ai_margin.config.tools_hash": "tools",
      "ai_margin.config.params_hash": "params",
      "ai_margin.config.identity": "served-config",
      "ai_margin.config.identity_weak": true,
      "ai_margin.http_status": 201,
    });
  });
});
