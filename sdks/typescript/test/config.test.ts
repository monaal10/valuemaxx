/**
 * resolveConfig endpoint normalization — the OTLP collector lives at `/v1/traces`.
 *
 * The backend's OTLP/HTTP collector is mounted at `POST /v1/traces`. Following the
 * OTel convention for `OTEL_EXPORTER_OTLP_ENDPOINT`, a *base* endpoint (no path, or
 * just `/`) gets `/v1/traces` appended, so a user who writes
 * `endpoint: "http://127.0.0.1:8000"` reaches the collector — not the root (404).
 * An endpoint that already carries a path (e.g. ends in `/v1/traces`, or a custom
 * gateway path) is used verbatim, so a deliberate full URL is never mangled.
 */

import { describe, expect, it } from "vitest";

import { resolveConfig } from "../src/index.js";

const BASE = { tenantId: "t", ingestKey: "ik" } as const;

describe("resolveConfig endpoint normalization", () => {
  it("appends /v1/traces to a base endpoint with no path", () => {
    expect(resolveConfig({ ...BASE, endpoint: "http://127.0.0.1:8000" }).endpoint).toBe(
      "http://127.0.0.1:8000/v1/traces",
    );
  });

  it("appends /v1/traces to a base endpoint whose path is just a slash", () => {
    expect(resolveConfig({ ...BASE, endpoint: "https://ingest.valuemaxx.dev/" }).endpoint).toBe(
      "https://ingest.valuemaxx.dev/v1/traces",
    );
  });

  it("leaves an endpoint that already targets /v1/traces untouched", () => {
    const url = "https://ingest.valuemaxx.dev/v1/traces";
    expect(resolveConfig({ ...BASE, endpoint: url }).endpoint).toBe(url);
  });

  it("leaves a custom-path endpoint verbatim (a deliberate full URL is never mangled)", () => {
    const url = "https://gw.example.com/otel/custom";
    expect(resolveConfig({ ...BASE, endpoint: url }).endpoint).toBe(url);
  });

  it("preserves a port and base path when appending", () => {
    expect(resolveConfig({ ...BASE, endpoint: "http://localhost:4318" }).endpoint).toBe(
      "http://localhost:4318/v1/traces",
    );
  });

  it("still rejects a non-http(s) endpoint", () => {
    expect(() => resolveConfig({ ...BASE, endpoint: "ftp://nope" })).toThrowError(
      /endpoint must be http/,
    );
  });
});
