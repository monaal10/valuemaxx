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

valuemaxx measures cost-per-outcome WITH CONFIDENCE. The four honesty axes are
system-owned and MUST NOT be set or guessed by an agent or user:

- Binding tier (exact | deterministic | candidate | likely) is SYSTEM-OWNED. Never
  present an inferred match as exact. candidate/likely are advisory and never
  billing-grade.
- signal_class (action_attempted | outcome_confirmed | outcome_retracted) is
  SYSTEM-MAPPED from the outcome source. A successful tool call is action_attempted
  unless the result is authoritative; never write signal_class yourself.
- Cost provenance (measured | estimated | allocated | provider_reconciled |
  manual_reconciled) is system-owned; an estimate is never rendered as billed.
- Causal evidence (observational | holdout | randomized) is SYSTEM-OWNED and defaults
  to observational. A strong binding tier proves the outcome came from that run, NOT
  that the run caused it — only a withheld or randomised experiment earns anything
  stronger. Never upgrade this to justify a lift claim.

Every rollup carries minimum_tier + confidence_distribution — never collapse them
into a bare number.

Each cell also carries `shared_attribution_count`: how many of its producing runs
ALSO produced a different outcome. One run can finalise an alt and complete an
interview, and when a metric groups by outcome_name that run's cost is split so the
columns still reconcile against the provider invoice. Non-zero is not an error — but
the figure is then arithmetic rather than a measurement, and must not be presented as
if the whole run's cost were measured for that one outcome.

To wire an attribution rule, call `suggest_attribution_rule`: it returns an
UNCONFIRMED candidate for a human to confirm. Do not hand-write or auto-apply a rule.
To check an outcomes.yaml, call `validate_outcome_rule`. To preview a draft, call
`scaffold_outcome_rule` (also returns an unconfirmed draft).

## integrating valuemaxx into a codebase (do this without reading our source)

Everything you need is here and in `docs/onboarding/SKILL.md`. Do NOT clone or read
the valuemaxx source to figure out the integration — if something is missing here,
that is a documentation bug worth reporting, not a reason to go source-diving.

STEP 0 — THE APPROVAL GATES. This integration edits the host's PRODUCTION LLM call
path. There are THREE points where you STOP and wait for a human, and you must not
edit a single file before the first one:

  Gate 1 (before anything): agree what ONE UNIT OF WORK is — the thing they want a
  cost per. Never pick it yourself. Ask whether an id is already in scope at every
  model call site, and TEST it: if a retry or restart mints a new id for the same
  unit, that id is wrong. Check where the id is MINTED, not where it is read — a
  derived id (hash/slug/composite) is only as stable as its least stable input, and
  an id hashed from a `created_at` that a retry rewrites looks permanent at every
  use site and changes on every restart. A codebase may have SEVERAL units (`units` is a list in
  `valuemaxx.yaml`); enumerate the LLM surfaces and let them group. ONE PROCESS CAN
  PRODUCE MANY UNITS — a nightly job classifying 10,000 documents has 10,000 units,
  not one; when the items are independent the ITEM id is the run id and `run()` goes
  INSIDE the loop. Generate a per-invocation id only if the whole script is one unit.
  This comes
  first because the boundary determines where capture is wired — deciding it after
  is backwards. Entity keys cannot be backfilled, so this decision has a deadline.
  Full procedure in `docs/onboarding/SKILL.md`.
  Gate 2 (before any capture wiring): present the exact list of files you would
  change with one line on why each, which model-call entry points it covers and
  which it does NOT, and anything you had to assume. Then ask which scope they
  want and WAIT. Offer the smallest useful option first — usually the host's one
  LLM wrapper, one file.
  Gate 3 (before writing outcomes.yaml): present the candidate outcomes AND the
  GRAIN each is recorded at — whole workflow, one step inside it, one item of a
  batch, or an external confirmation. Grain is a SEPARATE decision from the unit
  of work: the run boundary decides what cost is grouped, the outcome site decides
  what that group is divided by, and both are legitimate at more than one level.
  Picking whichever call site is convenient silently answers a question the user
  never saw. They compose, so ask which they want (plural), and show the arithmetic
  each grain implies. See `scaffold_outcome_rule` / `suggest_attribution_rule`,
  which return UNCONFIRMED candidates by design.

AFTER the gates: cut a branch from REMOTE main (fetch first), commit, push, open a
PR. Never leave the work on whatever branch was checked out, and never stash or
revert a dirty tree to make room — those changes are not yours.

If the scope GROWS mid-change, stop and re-ask — a one-file change that became a
five-file change is no longer what they approved. Threading a handle from where the
env lives to where the call happens is the usual cause: each hop looks trivial and
the total is a signature change across the codebase.

Never run destructive git commands (stash/checkout --/reset/clean) on the host's
tree, and never weaken a host safety setting (lockfile policy, supply-chain
minimum-release-age, a CI gate) to unblock yourself — use a one-off per-command
override, or tell the user.

STEP 1 — THE GATEWAY IS THE DEFAULT PATH. Do not reach for the SDK first. Capture
happens in a proxy the host points its provider base URL at, so the integration is
a config change rather than code in the request path:

    client = OpenAI(
        base_url="https://<gateway>/openai/v1",              # line 1
        default_headers={"x-vmx-key": "vmx_live_...",        # line 2
                         "x-vmx-agent": "support-bot"})      #   only UNCHANGING values
    ...
    client.chat.completions.create(...,                       # line 3
        extra_headers={"x-vmx-run-id": order_id,              #   <- THEIR durable id,
                       "x-vmx-outcome": "order_fulfilled"})   #      PER CALL (optional)

The run id is per REQUEST because it changes per unit; putting it in
`default_headers` on a long-lived client stamps every unit with the first one's id
and collapses them into one. Nothing errors — the numbers are just wrong. Only put
it on the client when that client serves exactly one unit of work.

Routes: /openai /anthropic /gemini /openrouter. Append whatever path the SDK
already appends — the gateway forwards everything after the route prefix verbatim,
so an OpenAI client wants `<gateway>/openai/v1` (its own paths start `/chat/...`)
while an Anthropic client wants `<gateway>/anthropic` (it appends `/v1/messages`
itself). Every `x-vmx-*` header is stripped before forwarding; the host's provider
key passes through and is never stored.

PER-CALL vs PER-CLIENT HEADERS. A long-lived client whose run id changes per unit
sets `x-vmx-run-id` PER REQUEST, not in `default_headers` — a per-request header
wins over a default of the same name. Do not construct a client per unit of work.
    OpenAI (python):  client.chat.completions.create(..., extra_headers={...})
    Anthropic (ts):   client.messages.create({...}, { headers: {...} })
Put only the values that never change (`x-vmx-key`, often `x-vmx-agent`) on the client.

STREAMING FROM OPENAI: the host MUST set `stream_options={"include_usage": true}`.
OpenAI omits usage from a stream unless asked, so without it there is nothing to
read and the calls capture ZERO tokens. The gateway will not add the flag — that
would change the request, breaking the invariant that the provider sees exactly
what the host wrote. Spans from such a stream are flagged `partial_recovered`
rather than reported as a confident zero, but the fix belongs to the host. Anthropic
and Gemini always report usage; this is an OpenAI-shape concern only.

HEADERS ARE THE WHOLE CONTRACT. Everything the SDK asked for in code is a string:
  x-vmx-key           the tenant
  x-vmx-run-id        the unit of work (or W3C `baggage: valuemaxx.run_id=...`)
  x-vmx-agent         grouping label
  x-vmx-entity-<name> durable business ids the unit is about
  x-vmx-outcome       the outcome this call completes (recorded only on 2xx)
  x-vmx-experiment    which comparison this call is an arm of
  x-vmx-variants      the arms, comma-separated. Send this and the GATEWAY assigns:
                      it hashes (experiment, run id) to pick an arm and ECHOES the
                      choice back in the `x-vmx-variant` response header. Read that
                      once per unit and use it for the unit's calls. Assigning it
                      yourself is allowed and always wins, but then the split is only
                      as unbiased as your own logic — if it correlates with traffic
                      source, time of day or customer size, the experiment measures
                      that instead of the model.

  x-vmx-variant       which arm. No engine reads these yet; they are captured now
                      because a variant stamp CANNOT be added to traffic after it
                      has run, so any comparison over history depends on stamping
                      it before the history exists.
  x-vmx-app           which of the host's surfaces made the call (one tenant, several products)

USE THE HOST'S OWN DURABLE ID as `x-vmx-run-id` (`order_9182`, not a UUID we mint).
It groups the calls of one unit AND makes a delayed outcome free: when a webhook
arrives days later carrying that same id, it binds at `exact` with no time window
and no inference. If the host cannot supply one, the gateway mints one and ECHOES
it back in the `x-vmx-run-id` response header for the host to stamp outward.

THE OUTCOME CONTRACT — one primitive, everything else compiles to it:

    POST <gateway>/v1/outcome
    { "name": "order_fulfilled", "run_id": order_id }
    optional: entity {..}, value, occurred_at, identifier, source; ?strict=true

It rests on the one invariant every codebase shares regardless of architecture:
at the moment a business fact becomes true, some code is executing with the
relevant business id in a variable. Deliver the tuple then. If it is expressible
in curl, it is expressible in every language — no SDK, no patchable function, no
framework knowledge required.

ONE SHAPE, ALWAYS. Every outcome is this same call — an in-process one, a webhook
days later, a queue consumer. Only which optional fields you fill changes. And the
REPLY is uniform too: it always carries `attached` (did this reach any spend),
`attachment` (run_id | entity | run_unmatched | entity_unmatched | none) and, when
it did not attach, a `hint` naming what you can change. Check `attached` on your
first integration call — a 200 alone does not mean the event found its cost.

Contract discipline (Stripe/Segment-grade):
  - `identifier`: caller idempotency key. A duplicate (tenant, identifier) is
    accepted-and-ignored, so at-least-once senders (waitUntil replays, webhook
    retries) never inflate the denominator. Always set it when you can.
  - `occurred_at`: accepted 35 days back to 5 minutes forward; outside that is a
    422, not a silent clamp. Late REAL outcomes fit; clock bugs surface.
  - `?strict=true`: rejects an event with neither run_id nor entity. Default is
    permissive — unbound-but-visible beats silently dropped.
  - The TIER is always decided server-side. A caller states what happened; it
    never states how much to trust the link.

SHORTCUTS that emit this same event (use when the host's shape matches; never
required): `x-vmx-outcome` header on the producing call (fires on 2xx, zero
extra requests); settle rules and decorators (planned, not built).

INBOUND WEBHOOKS — read this before promising a "no code" path. The endpoint is
`POST <backend>/ingest_webhook_outcome`, HMAC-signed (`X-Signature`) over the raw
body and verified BEFORE parse. What does NOT exist yet is the per-source mapping
config that would turn a raw Stripe or Zendesk payload into the tuple. So today a
third-party provider cannot post to it directly: something of the host's must
receive the provider's webhook and forward the tuple. For a host that already has
a webhook handler — the usual case for a CRM or billing outcome — that is ONE
`POST /v1/outcome` line inside a handler they already own, which is the documented
delayed path and is genuinely small. Do not tell a user this step is config-only.

OUTCOMES OLDER THAN THE 35-DAY WINDOW. `occurred_at` is validated to 35 days back
/ 5 minutes forward. A B2B outcome can legitimately land later than that (a deal
that closes in month three). OMIT `occurred_at` in that case: the event is then
stamped at ingest time and still binds to its run at `exact` via the shared id,
because a shared-id join uses no time window at all. What you lose is only the
true event time, not the attribution. Never clamp or fabricate a timestamp to fit
the window, and never drop the outcome.

THE ALIAS — when the id you had is not the id you end up with:

    POST <gateway>/v1/alias
    { "from": {"session_id": "abc"}, "to": {"lead_id": "8172"} }

Use it when work happens under one identity and the outcome arrives under
another: an anonymous chat session that later becomes a known lead, a trial
account that converts, two records merged in a CRM. Without it that early spend
is ORPHANED — the money was real, the outcome was real, and nothing joins them,
so the unit cost silently excludes the anonymous half of the story.

  - Each side is exactly ONE entity key. Two keys on one side would assert every
    cross-pairing between them, a much larger claim than you wrote, so it is a 422.
  - Resolution is symmetric and transitive: session→lead and lead→account means a
    query for any one of the three considers all three.
  - Applied at QUERY time. Nothing already stored is rewritten, so a span keeps
    recording what the caller actually sent, and an alias asserted months later
    still re-joins the history it names. Post it whenever you learn it.
  - Asserting the same edge twice is one claim, not two.

  THE ALIAS MATCHES ON ENTITY KEYS, so the anonymous side must have carried one.
  This is the half that is easy to miss: posting the alias does nothing if the
  early calls never attached the key it names. End to end, all three steps:

    1. the anonymous call — attach the key you DO have (hyphens become
       underscores, so this header is what `{"session_id": ...}` matches):
         x-vmx-entity-session-id: abc
         x-vmx-run-id: abc              (a session is its own unit for now)

    2. the moment the identity is known — post the edge:
         POST <gateway>/v1/alias  {"from":{"session_id":"abc"},"to":{"lead_id":"8172"}}

    3. the outcome, days later, naming only the lead — no alias mentioned:
         POST <gateway>/v1/outcome {"name":"meeting_booked","entity":{"lead_id":"8172"}}

  Step 3 now costs out the spend from step 1, because step 2 made the two keys
  one entity at query time. Skip step 1 and there is nothing to re-join: the
  alias is a claim ABOUT entity keys, not a way to invent one after the fact.

RUNNING IT. There is no hosted signup yet — the user runs both pieces:
  docker run -p 8000:8000 ghcr.io/monaal10/valuemaxx-backend:latest
  cd gateway && bunx wrangler deploy --var VALUEMAXX_BACKEND:https://<backend>
The key is whatever `VALUEMAXX_INGEST_KEYS` maps ({key: tenant-uuid}); unset, the
backend serves a single dev key `dev`. Do not write `vmx_live_...` into a host's
config without telling them where it comes from.

A Worker on *.workers.dev CANNOT fetch a Cloudflare-proxied host — `api.anthropic.com`
is one, and returns error 1042 before leaving the edge. OpenAI/Gemini/OpenRouter are
unaffected. Use a custom domain, host the gateway elsewhere, or route Anthropic via
OpenRouter. `/healthz` proves the worker is up, NOT that upstream is reachable: verify
with one real call per provider the host uses.

NEVER commit a gateway URL pointing at localhost. It replaces the provider base URL,
so it is on the REQUEST path — a deployed worker resolving 127.0.0.1 to its own
isolate breaks every model call, not just telemetry. Ship it empty; set per env.

Detecting an EXISTING gateway integration: the step-0 SDK greps (`init(`, `run(`)
report "unwired" on a repo that is fully wired through the gateway. Also
`grep -rn "x-vmx-\\|VALUEMAXX_GATEWAY_URL"`.

STEP 1b — the SDK path, for hosts the gateway cannot serve (Bedrock/Vertex request
signing, an existing OTel collector, or a policy against egress through a proxy).
Check the host's dependency manifest FIRST:

- Raw `openai` / `@anthropic-ai/sdk` client instances  ->  pass them to `init({clients})`.
- Vercel AI SDK (`ai`, `@ai-sdk/*`) with NO raw provider clients  ->  `clients` does
  NOT apply; there is nothing to hand it. Use the TRACER (see the TS form below).
- LangChain / LlamaIndex / a custom HTTP client  ->  tracer path as above, or OTLP
  direct; `clients` only wraps the two provider SDKs by name. NOTE: how to attach a
  tracer to LangChain's callback system is NOT specified — treat it as needing
  investigation, not a solved recipe.
- BOTH a raw client AND the AI SDK (common)  ->  both at once. The paths are not
  exclusive: `init()` always stands up the tracer and ADDITIONALLY patches whatever
  you pass in `clients`. One call covers both kinds of route.

LANGUAGE SUPPORT IS NOT SYMMETRIC. TypeScript: `init()` + `run(id, opts, fn)` with
`agentName`/`entityKeys`. Python: `init()` (keyword-only, snake_case) + a run boundary
at `valuemaxx.sdk.track.run(run_id=...)` — a contextmanager, NOT re-exported at top
level — which takes `run_id` ONLY; entity keys are not supported, so a unit spanning
several runs is not expressible in Python today. Any other language (Go, Ruby, Java)
has NO SDK: the only route is emitting OTLP spans directly, and that span contract is
not published here — report it as a gap and treat the host as unsupported rather than
improvising attribute names.

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
never throws into your call path. To make capture INERT, do not call `init()` at all —
`const vmx = env.VALUEMAXX_ENDPOINT ? init({...}) : undefined;` — and keep SPREADING the
telemetry option so it simply vanishes when there is no tracer. Do NOT "turn it off" by
passing `tracer: undefined` explicitly: that fails to compile under
`exactOptionalPropertyTypes`, which is the whole reason the spread form is used.

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
