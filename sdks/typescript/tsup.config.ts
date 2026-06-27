import { defineConfig } from "tsup";

/**
 * Dual ESM/CJS build with bundled `.d.ts` declarations.
 *
 * The OpenTelemetry packages stay external (peer-resolved by the host) so the
 * published tarball ships only valuemaxx's own code; the host deduplicates a
 * single OTel API instance, which is required for context propagation to work.
 */
export default defineConfig({
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
});
