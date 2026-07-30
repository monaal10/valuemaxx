"""Generate ``llms.txt`` from the capability registry (the agent-integration surface).

Agents read installed source and integration files; ``llms.txt`` is the single,
generated index of everything the product exposes. It lists EVERY capability (name,
surfaces, mode, description) and an ``instructions`` section that corrects the priors
an LLM agent is likely to bring: the honesty axes are system-owned (binding tier is
system-owned, signal_class is system-mapped — never user-set), and an attribution
rule should be drafted via ``suggest_attribution_rule`` (which returns an unconfirmed
candidate a human confirms) rather than guessed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from valuemaxx.capabilities import Surface

if TYPE_CHECKING:
    from valuemaxx.capabilities import AnyCapability, Registry

_INSTRUCTIONS = """\
## instructions (read before calling any capability)

valuemaxx measures cost-per-outcome WITH CONFIDENCE. The three honesty axes are
system-owned and MUST NOT be set or guessed by an agent or user:

- Binding tier (exact | deterministic | candidate | likely) is SYSTEM-OWNED. Never
  present an inferred match as exact. candidate/likely are advisory and never
  billing-grade.
- signal_class (action_attempted | outcome_confirmed | outcome_retracted) is
  SYSTEM-MAPPED from the outcome source. A successful tool call is action_attempted
  unless the result is authoritative; never write signal_class yourself.
- Cost provenance (measured | estimated | allocated | provider_reconciled |
  manual_reconciled) is system-owned; an estimate is never rendered as billed.

Every rollup carries minimum_tier + confidence_distribution — never collapse them
into a bare number.

To wire an attribution rule, call `suggest_attribution_rule`: it returns an
UNCONFIRMED candidate for a human to confirm. Do not hand-write or auto-apply a rule.
To check an outcomes.yaml, call `validate_outcome_rule`. To preview a draft, call
`scaffold_outcome_rule` (also returns an unconfirmed draft).

## integrating valuemaxx into a codebase (do this without reading our source)

Everything you need is here and in `docs/onboarding/SKILL.md`. Do NOT clone or read
the valuemaxx source to figure out the integration — if something is missing here,
that is a documentation bug worth reporting, not a reason to go source-diving.

STEP 1 — pick the capture path from the host's LLM stack. This is the fork agents
most often get wrong. Check the host's dependency manifest FIRST:

- Raw `openai` / `@anthropic-ai/sdk` client instances  ->  pass them to `init({clients})`.
- Vercel AI SDK (`ai`, `@ai-sdk/*`) with NO raw provider clients  ->  `clients` does
  NOT apply; there is nothing to hand it. Use the TRACER (see the TS form below).
- LangChain / LlamaIndex / a custom HTTP client  ->  tracer path as above, or OTLP
  direct; `clients` only wraps the two provider SDKs by name.

The complete TypeScript form (single entrypoint; there is no subpath export):

    import { init, run } from "valuemaxx";
    const vmx = init({
      tenantId: process.env.VALUEMAXX_TENANT_ID,   // a plain STRING (Python uses a UUID)
      ingestKey: process.env.VALUEMAXX_INGEST_KEY, // secret; never log it
      endpoint: process.env.VALUEMAXX_ENDPOINT,    // http(s); no default exists
    });
    // `tracer` is `Tracer | undefined` (undefined if the exporter failed to start).
    // SPREAD it — passing `tracer: undefined` fails under exactOptionalPropertyTypes.
    await generateText({ model, prompt,
      ...(vmx.tracer
        ? { experimental_telemetry: { isEnabled: true, tracer: vmx.tracer } }
        : {}) });
    await run("checkout-agent-42", async () => { /* calls here bind to this run id */ });

`forceFlush`/`shutdown` are METHODS on the result — call `vmx.forceFlush()`; don't
destructure them off. Call `init()` ONCE per process/isolate (it stands up an OTLP
exporter + batch span processor); calling it per request rebuilds and leaks them.
To name the tracer type in your own signatures without adding `@opentelemetry/api`:
`type VmxTracer = NonNullable<ReturnType<typeof init>["tracer"]>`.

`init()`'s CONFIG VALIDATION throws (`InitConfigError`) on a missing/non-http endpoint —
that is a call-site programming error, deliberately not a silent degrade. Everything
after validation is fail-open (caught, logged, surfaced on `InitResult.warnings`), so it
never throws into your call path. To make capture INERT, do not call `init()` at all and
pass `tracer: undefined` — the AI SDK ignores it.

Find EVERY model-construction path before editing. "Thread it once through the wrapper"
assumes a single funnel; real codebases often have a primary wrapper plus bypasses that
build a model directly and call `streamText` themselves. Grep every `generateText`/
`streamText` call site — a bypass you miss captures nothing, silently.

Short-lived runtimes (Workers/Lambda) have no process exit to flush on: call the returned
`forceFlush()` before the isolate is frozen (e.g. in `ctx.waitUntil(...)`).

What leaves the process, and what it costs (answer this before a host signs off):
- Token counts + call metadata (model, provider, timings, run id, tenant id) ONLY.
  Prompt and response CONTENT is NOT captured unless the host opts in with
  `captureContent: true` — it defaults to false. Say this explicitly when integrating
  into a codebase that handles personal data.
- Export is batched and asynchronous (`BatchSpanProcessor`), off the request hot path.
  If the endpoint is unreachable, telemetry is dropped and counted — the SDK never
  blocks or fails the host's LLM call.
- The ingest key is held in a `SecretString` that never appears in a log, a thrown
  error, or a serialized config echo.

STEP 2 — runtime. Node >= 20. The SDK needs `node:async_hooks` (AsyncLocalStorage, for
the in-process run-id carry) and `node:crypto`. On Cloudflare Workers/workerd this
means `nodejs_compat` must be enabled; with it, capture works. Deno/Bun: async_hooks
support varies — verify `run()` binds before relying on `exact` tier.

STEP 3 — the backend. Cost spans go to a valuemaxx backend you run; there is no
default hosted endpoint. `docker run -p 8000:8000 valuemaxx-backend` (or
`valuemaxx up` with Python) and point `endpoint` at it with `ingestKey: "dev"`. If the
host has not decided where to run it, wire capture so it is INERT unless the endpoint
env var is set — never invent an endpoint, and never point telemetry at a host the
user did not choose.

STEP 4 — outcomes (optional; capture alone already gives per-model/per-agent spend).
Run `valuemaxx onboard --repo <dir>` for a read-only scan that proposes UNCONFIRMED
candidate rules plus a reviewable diff. It writes nothing. It skips test/fixture code
and module-scope sites, because a rule can only bind to a named production function.
Present the proposal to the human and let them confirm before writing outcomes.yaml.

Reviewing an `onboard` proposal: a `tier: candidate` rule is a GUESS awaiting human
confirmation, never billing-grade. Do not upgrade a tier to make a number look better.
"""


def _surface_names(cap: AnyCapability) -> str:
    return "|".join(
        surface.name for surface in Surface if surface in cap.surfaces and surface.name is not None
    )


def _capability_line(cap: AnyCapability) -> str:
    return (
        f"- {cap.name} [surfaces={_surface_names(cap)}; mode={cap.mode.value}]: {cap.description}"
    )


def generate_llms_txt(registry: Registry) -> str:
    """Generate the ``llms.txt`` index for ``registry`` (lists every capability).

    Deterministic: capabilities are listed in registration order. The output has a
    title, a capabilities list (one line per capability with its surfaces + mode),
    and the system-owned-axes instructions section.
    """
    lines = [
        "# valuemaxx — AI margin intelligence (cost-per-outcome with confidence)",
        "",
        "## capabilities",
        "",
    ]
    lines.extend(_capability_line(cap) for cap in registry.all())
    lines.extend(["", _INSTRUCTIONS])
    return "\n".join(lines)


__all__ = ["generate_llms_txt"]
