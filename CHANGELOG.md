# Changelog

All notable changes to valuemaxx. This project follows [Semantic Versioning](https://semver.org/).
Pre-1.0, the public API may change between minor versions; the pip and npm packages
always ship the same version (see [RELEASING.md](./RELEASING.md)).

## [0.3.0] — 2026-08-18

The release that makes cost-per-outcome correct for **delayed** outcomes — work whose
result is confirmed hours or months later, in another process, under another id. That
is the case the product exists for, and several parts of it were quietly wrong.

### Fixed — numbers that were wrong

- **Entity-bound outcomes charged the whole window's spend.** Cost was narrowed to the
  runs that produced an outcome only when the outcome carried a run id. An outcome
  bound by *entity* — a CRM confirming a meeting days later with only `lead_id` — fell
  through to all spend in the window, so "cost per meeting" was portfolio spend ÷
  meetings, charging every unrelated and failed run to the successes.
- **A shared run's cost was halved on ungrouped metrics.** The split that stops one run
  double-counting across grouped columns was applied unconditionally, so an ungrouped
  cost-per-outcome reported $2.50 of a $5.00 invoice. Under-reporting is the dangerous
  direction: overshooting the provider bill is caught the first time anyone reconciles.
- **The entity-match window was a single global 24 hours.** Anything slower bound to
  nothing at all, silently. It is now declared per outcome (`entity_window_days`),
  because only the caller knows whether their lag is an hour or a quarter.
- **`POST /v1/alias` failed against a real database** — the route passed a string to a
  UUID column. It had only ever been exercised against test doubles.

### Added

- **Entity aliasing** (`POST /v1/alias`). Work that starts anonymous (`session_id`) and
  later becomes known (`lead_id`) no longer orphans its spend. Resolution is a
  transitive, symmetric closure applied at *query* time, so nothing already captured is
  rewritten and an alias asserted months later still re-joins the history it names.
- **The optimization loop.** `evaluate_switch` compares cost **per outcome** on both
  sides, not cost per token — a model that halves the token bill while dropping the
  outcome rate has made each outcome dearer, and only this framing catches it. It runs
  a **non-inferiority** test (the right question for a cost-saving switch; superiority
  would reject every good one) and reports what each confidence bar would cost in units
  per arm, so a team can pick a bar it can afford to prove.
- **Gateway-side experiment assignment.** Declare arms with `x-vmx-variants` and the
  gateway assigns deterministically on `(experiment, run id)` — one unit stays in one
  arm across every call it makes — and echoes the choice back in `x-vmx-variant`.
  A host-set variant always wins.
- **`causal_evidence`**, the fourth honesty axis (`observational` / `holdout` /
  `randomized`). A strong binding tier proves an outcome came from a run, *not* that
  the run caused it; only a withheld or randomised experiment earns anything stronger.
- **`shared_attribution_count`** on every metric cell — how many of its runs also
  produced a different outcome, so a split figure never renders as a measured one.
- **`latency_ms`** on every span, plus `x-vmx-experiment` / `x-vmx-variant` /
  `x-vmx-app`. Captured now because a variant stamp cannot be added to traffic
  after the fact.

### Changed

- **Every outcome reply now states whether the event attached.** A 200 with a null tier
  used to mean two very different things — "carried a join key and matched nothing" and
  "carried no join key at all" — and both read as success. Replies now carry `attached`,
  `attachment` and, when unattached, a `hint` naming what the caller can change.
- **The dashboard leads with cost per outcome**, with every honesty signal rendered
  inline, unattributed spend as a visible row rather than an omission, and "insufficient
  data" as a named state instead of a bare dash.

### Documentation

Rewritten around the gateway and the outcome contract, after two blind-agent
onboarding tests. Both initially failed; the fixes include the OpenAI streaming
requirement (`stream_options.include_usage`, without which capture is silently zero),
per-call vs per-client headers, outcomes older than the 35-day window, and an honest
account of what the inbound-webhook path does *not* yet do.

## [0.2.2] — 2026-08-07

Earlier releases predate this changelog. See the git history for detail.
