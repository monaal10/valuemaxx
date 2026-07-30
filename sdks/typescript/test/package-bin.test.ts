/**
 * The published package must actually ship its `valuemaxx` executable.
 *
 * valuemaxx@0.1.0 shipped with NO `bin` field and no `dist/bin/`, so
 * `npx valuemaxx onboard` failed with "could not determine executable to run" for every
 * user. The cause was subtle: `bin` was declared as `"./dist/bin/valuemaxx.js"`, and npm
 * rejects the leading `./` — it STRIPS the entry at publish time with only a warning
 * ("bin[valuemaxx] script name ... was invalid and removed"). `npm pack --dry-run` shows
 * the file present either way, so the defect is invisible locally and only manifests in
 * the published tarball.
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const pkg = JSON.parse(
  readFileSync(fileURLToPath(new URL("../package.json", import.meta.url)), "utf8"),
) as {
  bin?: Record<string, string>;
  files?: string[];
  repository?: { url?: string; directory?: string };
};

describe("published package bin", () => {
  it("declares the valuemaxx executable", () => {
    expect(pkg.bin?.valuemaxx).toBeDefined();
  });

  it("declares the bin path WITHOUT a leading './' (npm strips such entries on publish)", () => {
    expect(pkg.bin?.valuemaxx?.startsWith("./")).toBe(false);
  });

  it("ships the dist/ directory that contains the bin", () => {
    expect(pkg.files ?? []).toContain("dist");
  });
});

// npm publishes with provenance by default under OIDC trusted publishing, and sigstore
// REJECTS the upload if `repository.url` does not match the repo the workflow ran in:
//   422 ... "repository.url" is "", expected to match "https://github.com/<org>/<repo>"
// The manifest carried no `repository` at all, so every provenance publish 422'd.
describe("provenance metadata", () => {
  it("declares repository.url matching the GitHub repo", () => {
    expect(pkg.repository?.url).toBe("git+https://github.com/monaal10/valuemaxx.git");
  });

  it("declares the monorepo subdirectory the package lives in", () => {
    expect(pkg.repository?.directory).toBe("sdks/typescript");
  });
});
