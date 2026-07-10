import { defineConfig } from "tsup";

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
    outExtension() {
      return { js: ".js" };
    },
  },
]);
