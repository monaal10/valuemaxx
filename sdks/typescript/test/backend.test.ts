/**
 * Backend lifecycle preflight — the failure paths a user actually hits first.
 *
 * `valuemaxx up` shells out to Docker, so the two things that must never happen are a
 * raw spawn error and a misleading diagnosis. Both regressions below were real:
 *
 *  - `docker info` exits **0** with an empty ServerVersion when Docker Desktop is not
 *    running. Trusting the exit code let a dead daemon pass the preflight, and the run
 *    then failed later as "could not query Docker for the backend container".
 *  - `docker ps` exits non-zero with EMPTY stdout and the error on stderr. Reading a
 *    combined stdout+stderr string made a dead daemon look like a *stopped container*,
 *    so `up` tried to `docker start` a container it had never confirmed existed.
 */

import { describe, expect, it } from "vitest";

import { backendUrl, dockerHint } from "../src/onboarding/backend.js";

describe("docker preflight hints", () => {
  it("tells a user with no Docker how to install it, and why it is needed", () => {
    const hint = dockerHint("not-installed");
    expect(hint).toContain("Docker was not found");
    expect(hint).toContain("docs.docker.com");
    // The "why" matters: without it this reads as an arbitrary dependency.
    expect(hint).toContain("install Python");
  });

  it("distinguishes an installed-but-stopped daemon from a missing install", () => {
    const stopped = dockerHint("daemon-down");
    expect(stopped).toContain("daemon isn't running");
    expect(stopped).not.toContain("docs.docker.com/get-started");
    expect(stopped).not.toEqual(dockerHint("not-installed"));
  });

  it("never surfaces a raw spawn error", () => {
    for (const reason of ["not-installed", "daemon-down", undefined]) {
      const hint = dockerHint(reason);
      expect(hint).not.toContain("ENOENT");
      expect(hint).not.toContain("spawnSync");
      expect(hint.startsWith("valuemaxx:")).toBe(true);
    }
  });
});

describe("backendUrl", () => {
  it("defaults to port 8000 on loopback", () => {
    expect(backendUrl()).toBe("http://127.0.0.1:8000");
  });

  it("honors an explicit port", () => {
    expect(backendUrl(9999)).toBe("http://127.0.0.1:9999");
  });
});
