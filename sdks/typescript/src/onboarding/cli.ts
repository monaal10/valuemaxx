/**
 * The `valuemaxx` command's onboard entry (npm). `valuemaxx onboard [--repo <dir>]` scans a
 * TS/JS repo and prints a proposed `outcomes.yaml` + a reviewable diff — identical in behavior
 * to the Python `valuemaxx onboard` (a golden parity test enforces the equivalence).
 *
 * Read-only: nothing is written; the candidate rules are UNCONFIRMED until a human reviews the
 * diff. `typescript` is an optional peer dependency (used only here, for parsing) — a TS repo
 * already has it; if it's genuinely absent, we print an install hint rather than a stack trace.
 */

function parseRepo(argv: readonly string[]): string {
  const i = argv.indexOf("--repo");
  if (i !== -1 && i + 1 < argv.length) return argv[i + 1]!;
  return process.cwd();
}

export async function main(argv: readonly string[] = process.argv.slice(2)): Promise<number> {
  const [command, ...rest] = argv;

  if (command === undefined || command === "--help" || command === "-h") {
    process.stdout.write(
      "valuemaxx — AI margin intelligence.\n\n" +
        "Usage:\n" +
        "  valuemaxx onboard [--repo <dir>]   Scan a repo -> propose outcomes.yaml + a reviewable diff\n",
    );
    return 0;
  }

  if (command !== "onboard") {
    process.stderr.write(`valuemaxx: unknown command '${command}'. Try 'valuemaxx onboard'.\n`);
    return 2;
  }

  const repo = parseRepo(rest);

  // `onboard` needs the TypeScript compiler to parse. Import lazily so a missing peer dep is a
  // friendly hint, not a crash — and so the SDK library itself never pulls typescript.
  try {
    await import("typescript");
  } catch {
    process.stderr.write(
      "valuemaxx onboard needs the TypeScript compiler to parse your code, but 'typescript' " +
        "is not installed.\nInstall it (your TS project usually already has it):  npm i -D typescript\n",
    );
    return 1;
  }

  const { onboard, renderOnboard } = await import("./onboard.js");
  process.stdout.write(`valuemaxx onboard: scanning ${repo} -> propose -> render -> diff.\n\n`);
  process.stdout.write(renderOnboard(onboard(repo)) + "\n");
  return 0;
}
