/**
 * `valuemaxx up` / `valuemaxx view` — run the backend without knowing what it is.
 *
 * THE POINT: valuemaxx is language-agnostic in the way promptfoo is — not because
 * everything is written in one language, but because the CLI hides where the work
 * happens. The backend is a Python FastAPI app (~20k lines: ingest, store, outcomes,
 * reconciliation, metrics, eval); a TS user must never install Python, learn a
 * `docker run` incantation, or start a second process by hand. They type
 * `npx valuemaxx up` and get a URL.
 *
 * We shell out to the published image rather than reimplementing the backend in Node.
 * A second backend would mean two implementations of the binding cascade, the metric
 * DSL, and the reconciliation rules — drifting silently, with the honesty labels
 * (binding tier / signal class / cost provenance) as the thing that drifts. One
 * backend, many front doors.
 *
 * DOCKER IS THE ONE PREREQUISITE, and we say so plainly rather than failing with a
 * raw ENOENT. That is a real difference from promptfoo (which has none, because it
 * never runs inside your app and needs no server). It is also a much smaller ask than
 * "install Python + pip + the right extras", and it is the only floor that keeps a
 * single backend implementation.
 *
 * The image is PINNED to this CLI's version: an older CLI must never silently drive a
 * newer backend whose API has moved. `latest` is a fallback only when the exact tag is
 * absent (a CLI released before its image finished publishing).
 */

import { spawn, spawnSync } from "node:child_process";

/** The container name we reuse, so `up` twice does not start two backends. */
const CONTAINER_NAME = "valuemaxx-backend";
const IMAGE_REPO = "ghcr.io/monaal10/valuemaxx-backend";
const DEFAULT_PORT = 8000;
/** Named volume so the embedded SQLite db survives `docker rm` — results persist. */
const DATA_VOLUME = "valuemaxx-data";

export type BackendOptions = {
  readonly port?: number | undefined;
  /** Image tag; defaults to this CLI's version so the pair cannot skew. */
  readonly version?: string | undefined;
};

/**
 * `stdout` and `stderr` are kept SEPARATE deliberately. A parsed command
 * (`docker ps --format ...`) must read stdout only: when the daemon is down, docker
 * exits non-zero with an empty stdout and an error on stderr, and a combined string
 * would look like real output — which read a dead daemon as "a stopped container".
 */
function run(
  cmd: string,
  args: readonly string[],
): { code: number; stdout: string; stderr: string } {
  const r = spawnSync(cmd, [...args], { encoding: "utf8" });
  return { code: r.status ?? 1, stdout: r.stdout ?? "", stderr: r.stderr ?? "" };
}

/** True iff a docker CLI exists AND its daemon is reachable (installed but stopped is common). */
export function dockerAvailable(): { ok: boolean; reason?: string } {
  const version = run("docker", ["--version"]);
  if (version.code !== 0) {
    return { ok: false, reason: "not-installed" };
  }
  // Detecting a stopped daemon needs the OUTPUT, not the exit code: `docker info` exits
  // 0 with an empty ServerVersion when Docker Desktop is not running (it reports client
  // info happily and only warns about the server). Trusting the status alone let a dead
  // daemon through, and the failure then surfaced as a confusing container-query error.
  const info = run("docker", ["info", "--format", "{{.ServerVersion}}"]);
  if (info.code !== 0 || info.stdout.trim() === "") {
    return { ok: false, reason: "daemon-down" };
  }
  return { ok: true };
}

/** The install/start hint for a missing prerequisite — never a raw spawn error. */
export function dockerHint(reason: string | undefined): string {
  if (reason === "daemon-down") {
    return (
      "valuemaxx: Docker is installed but its daemon isn't running.\n" +
      "Start Docker Desktop (or `sudo systemctl start docker`) and re-run.\n"
    );
  }
  return (
    "valuemaxx: the backend runs as a container, and Docker was not found.\n" +
    "Install it once — https://docs.docker.com/get-started/get-docker/ — then re-run.\n" +
    "\n" +
    "Why: the backend (ingest, outcomes, reconciliation, metrics, eval) is a single\n" +
    "service shared by every language SDK. Running it as an image is what keeps you\n" +
    "from having to install Python to use the TypeScript SDK.\n"
  );
}

/**
 * The state of the named container: running, stopped-but-present, or absent.
 *
 * A FAILED `docker ps` (daemon down, permission denied) is reported as "unknown", never
 * as "absent" or "stopped" — guessing there would make `up` try to `docker start` a
 * container it never confirmed exists, and surface the daemon error as a restart failure.
 */
export function containerState(): "running" | "stopped" | "absent" | "unknown" {
  const ps = run("docker", [
    "ps",
    "-a",
    "--filter",
    `name=^/${CONTAINER_NAME}$`,
    "--format",
    "{{.State}}",
  ]);
  if (ps.code !== 0) return "unknown";
  const state = ps.stdout.trim();
  if (state === "") return "absent";
  return state === "running" ? "running" : "stopped";
}

/** The URL the backend is served on. */
export function backendUrl(port: number = DEFAULT_PORT): string {
  return `http://127.0.0.1:${port}`;
}

/**
 * Start the backend if it is not already up. Idempotent: running `up` twice reuses the
 * existing container rather than failing on a name clash or starting a second copy.
 */
export function startBackend(opts: BackendOptions = {}): {
  ok: boolean;
  url: string;
  message: string;
} {
  const port = opts.port ?? DEFAULT_PORT;
  const url = backendUrl(port);

  const docker = dockerAvailable();
  if (!docker.ok) {
    return { ok: false, url, message: dockerHint(docker.reason) };
  }

  const state = containerState();
  if (state === "unknown") {
    // dockerAvailable() passed but the query still failed — report it rather than
    // guessing at a start/restart that will fail again with a confusing message.
    return {
      ok: false,
      url,
      message: "valuemaxx: could not query Docker for the backend container.\n",
    };
  }
  if (state === "running") {
    return { ok: true, url, message: `valuemaxx: backend already running on ${url}\n` };
  }
  if (state === "stopped") {
    const started = run("docker", ["start", CONTAINER_NAME]);
    if (started.code !== 0) {
      return {
        ok: false,
        url,
        message: `valuemaxx: could not restart the backend.\n${started.stderr}`,
      };
    }
    return { ok: true, url, message: `valuemaxx: backend restarted on ${url}\n` };
  }

  const tag = opts.version ?? "latest";
  const started = run("docker", [
    "run",
    "--detach",
    "--name",
    CONTAINER_NAME,
    "--publish",
    `${port}:8000`,
    "--volume",
    `${DATA_VOLUME}:/home/valuemaxx/data`,
    `${IMAGE_REPO}:${tag}`,
  ]);
  if (started.code !== 0) {
    // The pinned tag may not exist yet (CLI published before its image). Fall back to
    // `latest` ONCE, and say so — a silent version skew is worse than a slow start.
    if (tag !== "latest") {
      const fallback = run("docker", [
        "run",
        "--detach",
        "--name",
        CONTAINER_NAME,
        "--publish",
        `${port}:8000`,
        "--volume",
        `${DATA_VOLUME}:/home/valuemaxx/data`,
        `${IMAGE_REPO}:latest`,
      ]);
      if (fallback.code === 0) {
        return {
          ok: true,
          url,
          message:
            `valuemaxx: no backend image tagged ${tag}; started :latest instead.\n` +
            `valuemaxx: backend running on ${url}\n`,
        };
      }
      return {
        ok: false,
        url,
        message: `valuemaxx: could not start the backend.\n${fallback.stderr}`,
      };
    }
    return {
      ok: false,
      url,
      message: `valuemaxx: could not start the backend.\n${started.stderr}`,
    };
  }

  return {
    ok: true,
    url,
    message:
      `valuemaxx: backend running on ${url} (ingest key "dev")\n` +
      `valuemaxx: data persists in the ${DATA_VOLUME} volume; stop it with \`valuemaxx down\`.\n`,
  };
}

/** Stop the backend, leaving the data volume intact. */
export function stopBackend(): { ok: boolean; message: string } {
  const docker = dockerAvailable();
  if (!docker.ok) return { ok: false, message: dockerHint(docker.reason) };
  const state = containerState();
  if (state === "absent") {
    return { ok: true, message: "valuemaxx: no backend container to stop.\n" };
  }
  if (state === "unknown") {
    return { ok: false, message: "valuemaxx: could not query Docker for the backend container.\n" };
  }
  const stopped = run("docker", ["stop", CONTAINER_NAME]);
  if (stopped.code !== 0) {
    return { ok: false, message: `valuemaxx: could not stop the backend.\n${stopped.stderr}` };
  }
  return { ok: true, message: "valuemaxx: backend stopped (data kept).\n" };
}

/** Open a URL in the user's browser, best-effort — never fatal if it cannot. */
export function openBrowser(url: string): void {
  const opener =
    process.platform === "darwin" ? "open" : process.platform === "win32" ? "start" : "xdg-open";
  try {
    const child = spawn(opener, [url], { detached: true, stdio: "ignore" });
    child.unref();
  } catch {
    // A headless box has no browser; the caller already printed the URL.
  }
}
