/**
 * The `valuemaxx` command's onboard entry (npm). `valuemaxx onboard [--repo <dir>]` scans a
 * TS/JS repo and prints a proposed `outcomes.yaml` + a reviewable diff — identical in behavior
 * to the Python `valuemaxx onboard` (a golden parity test enforces the equivalence).
 *
 * Read-only: nothing is written; the candidate rules are UNCONFIRMED until a human reviews the
 * diff. `typescript` is an optional peer dependency (used only here, for parsing) — a TS repo
 * already has it; if it's genuinely absent, we print an install hint rather than a stack trace.
 */

/** Replaced at build time by tsup's `define`; absent when running from source. */
declare const __VALUEMAXX_VERSION__: string | undefined;

function parseRepo(argv: readonly string[]): string {
  const i = argv.indexOf("--repo");
  if (i !== -1 && i + 1 < argv.length) return argv[i + 1]!;
  return process.cwd();
}

function parsePort(argv: readonly string[]): number | undefined {
  const i = argv.indexOf("--port");
  if (i === -1 || i + 1 >= argv.length) return undefined;
  const parsed = Number.parseInt(argv[i + 1]!, 10);
  return Number.isFinite(parsed) ? parsed : undefined;
}

/**
 * This CLI's version, used to pin the backend image tag so an older CLI never silently
 * drives a newer backend. Injected at build time by tsup (`define`), falling back to
 * "latest" when running from source.
 */
const CLI_VERSION: string =
  typeof __VALUEMAXX_VERSION__ === "string" ? __VALUEMAXX_VERSION__ : "latest";

export async function main(argv: readonly string[] = process.argv.slice(2)): Promise<number> {
  const [command, ...rest] = argv;

  if (command === undefined || command === "--help" || command === "-h") {
    process.stdout.write(
      "valuemaxx — AI margin intelligence.\n\n" +
        "Usage:\n" +
        "  valuemaxx onboard [--repo <dir>]   Scan a repo -> propose outcomes.yaml + a reviewable diff\n" +
        "  valuemaxx up [--port <n>]          Start the backend (container; data persists)\n" +
        "  valuemaxx view [--port <n>]        Start the backend if needed, then open the dashboard\n" +
        "  valuemaxx down                     Stop the backend (keeps your data)\n",
    );
    return 0;
  }

  // Backend lifecycle. These shell out to the published backend image so a TS user never
  // installs Python or types a `docker run` — see backend.ts for why one backend, many
  // front doors, rather than a second implementation in Node.
  if (command === "up" || command === "view" || command === "down") {
    const { startBackend, stopBackend, openBrowser } = await import("./backend.js");

    if (command === "down") {
      const result = stopBackend();
      process.stdout.write(result.message);
      return result.ok ? 0 : 1;
    }

    const started = startBackend({ port: parsePort(rest), version: CLI_VERSION });
    process.stdout.write(started.message);
    if (!started.ok) return 1;
    if (command === "view") {
      process.stdout.write(`valuemaxx: opening ${started.url}\n`);
      openBrowser(started.url);
    }
    return 0;
  }

  if (command !== "onboard") {
    process.stderr.write(`valuemaxx: unknown command '${command}'. Try 'valuemaxx --help'.\n`);
    return 2;
  }

  const repo = parseRepo(rest);

  // `onboard` needs the TypeScript compiler to parse. Import lazily so a missing peer dep is a
  // friendly hint, not a crash — and so the SDK library itself never pulls typescript.
  let tsModule: unknown;
  try {
    tsModule = await import("typescript");
  } catch {
    process.stderr.write(
      "valuemaxx onboard needs the TypeScript compiler to parse your code, but 'typescript' " +
        "is not installed.\nInstall it (your TS project usually already has it):  npm i -D typescript\n",
    );
    return 1;
  }

  // typescript@7 is the native (Go) compiler: it ships `tsc` but NOT the JS parser API this
  // scanner uses, so `ts.createSourceFile` is undefined and we'd die with an opaque
  // "Cannot read properties of undefined (reading 'Latest')". Detect it and say so.
  const ts = (tsModule as { default?: unknown }).default ?? tsModule;
  if (typeof (ts as { createSourceFile?: unknown }).createSourceFile !== "function") {
    const version = (tsModule as { version?: string }).version ?? "unknown";
    process.stderr.write(
      `valuemaxx onboard needs the TypeScript JS parser API, but the installed 'typescript' ` +
        `(${version}) does not expose it.\nTypeScript 7 dropped the bundled JS API; install a 5.x/6.x ` +
        `alongside it:  npm i -D typescript@^5\n`,
    );
    return 1;
  }

  const { onboard, renderOnboard } = await import("./onboard.js");
  process.stdout.write(`valuemaxx onboard: scanning ${repo} -> propose -> render -> diff.\n\n`);
  process.stdout.write(renderOnboard(onboard(repo)) + "\n");
  return 0;
}
