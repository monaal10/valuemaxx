import { createRequire } from "node:module";

import { defineConfig } from "tsup";

// The CLI pins the backend image to its OWN version, so an older `valuemaxx up` never
// silently drives a newer backend. Read from the manifest the stamp script already owns.
const { version } = createRequire(import.meta.url)("./package.json") as { version: string };

/**
 * Dual ESM/CJS build with bundled `.d.ts` declarations.
 *
 * The OpenTelemetry packages stay external (peer-resolved by the host) so the
 * published tarball ships only valuemaxx's own code; the host deduplicates a
 * single OTel API instance, which is required for context propagation to work.
 */
export default defineConfig([
  // The SDK library (capture): dual ESM/CJS. Onboarding is NOT imported here, so the library
  // stays thin — no typescript/yaml pulled into the capture bundle.
  {
    entry: ["src/index.ts"],
    format: ["esm", "cjs"],
    dts: true,
    sourcemap: true,
    clean: true,
    treeshake: true,
    target: "es2022",
    outExtension({ format }) {
      return { js: format === "cjs" ? ".cjs" : ".js" };
    },
  },
  // The `valuemaxx` CLI bin (onboard). ESM only; `typescript` stays EXTERNAL (an optional
  // peer, imported lazily) so it's never bundled; `yaml` is bundled (a small real dep).
  {
    entry: { "bin/valuemaxx": "src/bin.ts" },
    format: ["esm"],
    dts: false,
    sourcemap: false,
    clean: false,
    treeshake: true,
    target: "es2022",
    external: ["typescript"],
    define: { __VALUEMAXX_VERSION__: JSON.stringify(version) },
    outExtension() {
      return { js: ".js" };
    },
  },
]);
