/**
 * The documented TypeScript integration snippet must stay TRUE of the real SDK.
 *
 * The docs' whole promise is that an agent can integrate valuemaxx without reading our
 * source. That promise breaks silently when the shipped types drift from the snippet — and
 * it did: the docs once showed `const { tracer } = init(...)` passed straight to
 * `experimental_telemetry`, which does not compile against `tracer: Tracer | undefined`
 * under `exactOptionalPropertyTypes`. These tests pin the API shape the docs describe.
 *
 * If one of these fails, fix the DOCS (docs/onboarding/SKILL.md + the `## integrating`
 * section generated into llms.txt) in the same change — not just the assertion.
 */

import { describe, expect, it } from "vitest";

import { init, run, activeRunId } from "../src/index.js";
import { InitConfigError } from "../src/config.js";

const CONFIG = {
  tenantId: "6f1c3b2a-0000-4a00-8000-000000000001",
  ingestKey: "dev",
  endpoint: "http://127.0.0.1:8000",
} as const;

describe("documented integration snippet", () => {
  it("exports init/run from the package root (no subpath export)", () => {
    expect(typeof init).toBe("function");
    expect(typeof run).toBe("function");
  });

  it("accepts tenantId as a plain string (the docs contrast this with Python's UUID)", () => {
    const vmx = init(CONFIG);
    expect(vmx.effective.tenantId).toBe(CONFIG.tenantId);
  });

  it("exposes forceFlush/shutdown as METHODS, so the docs must not destructure them", () => {
    const vmx = init(CONFIG);
    expect(typeof vmx.forceFlush).toBe("function");
    expect(typeof vmx.shutdown).toBe("function");
  });

  // The docs tell integrators to guard `vmx.tracer` rather than pass it through directly.
  // That instruction is only correct while `tracer` remains optional on InitResult.
  it("declares tracer as possibly-undefined (why the docs spread instead of passing it)", () => {
    const vmx = init(CONFIG);
    const telemetry = vmx.tracer
      ? { experimental_telemetry: { isEnabled: true, tracer: vmx.tracer } }
      : {};
    expect(typeof telemetry).toBe("object");
  });

  // "Inert" in the docs means NOT calling init() — because config validation throws rather
  // than degrading. If this ever stopped throwing, the documented inert pattern would be wrong.
  it("throws InitConfigError on a missing/non-http endpoint (so inert = don't call init)", () => {
    expect(() => init({ ...CONFIG, endpoint: "" })).toThrow(InitConfigError);
    expect(() => init({ ...CONFIG, endpoint: "ftp://nope" })).toThrow(InitConfigError);
  });

  it("binds a run id inside run() and leaves none outside (the `exact`-tier carry)", () => {
    expect(activeRunId()).toBeUndefined();
    run("checkout-agent-42", () => {
      expect(activeRunId()).toBe("checkout-agent-42");
    });
    expect(activeRunId()).toBeUndefined();
  });

  it("forceFlush() resolves even with no backend listening (never blocks the host)", async () => {
    const vmx = init(CONFIG);
    await expect(vmx.forceFlush()).resolves.toBeUndefined();
  });
});
