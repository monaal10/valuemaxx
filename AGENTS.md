# AGENTS.md — Engineering Standards (binding for all contributors, human and AI)

This file is the contract for how code is written in this repository. **AI agents (Claude Code, Cursor, etc.) and humans MUST follow it exactly.** It exists to stop drift into ad-hoc, untyped, untested code. `CLAUDE.md` points here; this is the source of truth.

> If a rule here conflicts with something you "remember" or a habit, **this file wins.** When unsure, stop and ask rather than guess.

---

## 0. The non-negotiables (read first)

1. **TDD always.** Write the failing test first. Red → Green → Refactor. No production code is written without a test that drove it. No exceptions.
2. **Strict typing, no escape hatches.** `pyright --strict` and `ruff` must pass with zero errors before any commit. No `Any` on public surfaces, no `# type: ignore` without a justifying comment and an issue link.
3. **No duplication.** Types are defined once, in `packages/core`. Behavior is defined once. If you're copy-pasting, stop and extract.
4. **The three honesty axes are invariants.** Cost provenance, binding tier, and outcome signal-class are system-owned, never user-settable, and are covered by tests. Never let an estimate render as billed, an inferred match render as exact, or an attempt render as a confirmed outcome.
5. **Surfaces are projections.** API/MCP/CLI are generated from the capability registry. Never hand-write a capability into one surface only.
6. **The ratchet (§5a).** Every bug becomes a permanent guardrail: regression test + a tightened type/lint/conformance rule + a documented rule, so the *class* can never recur. A fix without its guardrail is incomplete.

If you cannot satisfy all six for a change, the change is not done.

---

## 1. Test-Driven Development (TDD) — the loop

**Every feature and every bugfix follows red → green → refactor:**

1. **Red** — write a test that expresses the desired behavior and **watch it fail** for the right reason. A test that passes on first write is suspect; verify it actually exercises new behavior.
2. **Green** — write the *minimum* code to pass. No speculative generality.
3. **Refactor** — clean up with tests green. Extract duplication, improve names, keep the public surface typed.

**Never** write implementation first and tests after. **Never** comment out / `xfail` a failing test to "fix later" without an issue link and reviewer sign-off.

### The test pyramid — required at every stage

Every component ships with all three levels where applicable:

| Level | Scope | Rules |
|---|---|---|
| **Unit** | one function/class, isolated | fast (<100ms), no network, no real DB; mock only at true boundaries (never mock the thing under test). The bulk of tests. |
| **Integration** | across module/package boundaries | run against **real** Postgres (and ClickHouse where relevant) via testcontainers — **not** mocks. Covers capture→store, attribution→store, reconciliation, outcome-bind→store. |
| **E2E** | full user flow | SDK `init()` → capture → outcome bind → attribution → rollup; and the eval funnel discover→search→recommend. Exercises the real wire path (OTLP) and real storage. |

A PR that adds a capability without all applicable levels is incomplete. The reviewer checks for the pyramid explicitly.

### Test quality rules
- Test **behavior**, not implementation details. Don't assert on private internals.
- One logical assertion per test where reasonable; descriptive test names (`test_streaming_usage_recovered_when_final_chunk_present`).
- Property-based tests (Hypothesis) for the invariant-heavy code: token-vector math, proration, provenance propagation.
- Deterministic: no real clock/network/randomness — inject them. (Note: workflow scripts forbid `Date.now()`/`random()`; in app code, inject a clock/uuid provider so tests are reproducible.)
- Every fixed bug gets a regression test that fails before the fix.

---

## 2. Typing & static analysis

- **Python:** `pyright --strict` is the gate. `ruff check` + `ruff format` clean. `py.typed` shipped on every package.
- **No `Any` on public function signatures**, no `**kwargs: Any` on public APIs. Internal `Any` requires a comment.
- **No bare `# type: ignore`** — must be `# type: ignore[specific-code]  # reason + issue link`.
- **Pydantic v2 at every boundary** (wire, storage, config, capability I/O). Validate at the edge; trust types inside.
- **TypeScript SDK:** `tsconfig` with `"strict": true`, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`. No `any`; `unknown` + narrowing instead. ESLint + Prettier clean.
- Public enums are `Literal`/`StrEnum`, never loose strings.

---

## 3. Architecture rules (enforced, not aspirational)

1. **`packages/core` is the only place domain types live.** Every other package imports `Run`, `CostEvent`, `OutcomeEvent`, `AttributionResult`, `Confidence`, `Provenance`, etc. from it. Redefining a model elsewhere is a review-blocking error.
2. **Logic packages never import HTTP/MCP/CLI.** `capture`, `attribution`, `eval`, etc. expose **capabilities**; they must not know how they're served. A logic package importing FastAPI/typer/the MCP SDK is a blocking error.
3. **`apps/*` are thin projections.** API/MCP/CLI iterate the capability registry. Each capability **declares which surfaces it supports** (`surfaces=` mask) and a `mode` (`request_response | streaming | async_job | webhook_inbound`); a CI test asserts **"every capability appears on every surface it declares"** and **fails on drift**. (Streaming/async/webhook capabilities declare narrower surface sets — they are not force-fit into request/response.)
4. **Pluggable seams are honored.** New cost sources implement `CostSource`; new connectors implement `SourcePort`; storage is behind the storage port. Don't hardcode a provider/DB outside its adapter.
5. **No circular package dependencies.** Dependency direction flows toward `core`. Enforced by an import-linter contract in CI.

---

## 4. The honesty axes (domain invariants — tested)

These are the product's credibility. There are **exactly THREE system axes** (the eval `reliable`/`directional` grade is a per-recommendation label in the eval package, **not** a system axis — it does not ride every event). All three are enforced in code and covered by conformance tests:

- **Cost provenance** ∈ `measured | estimated | allocated | provider_reconciled | manual_reconciled`. (`manual_reconciled` = Bedrock/Vertex/Azure CSV-upload path.) Rules: never present `estimated` as billed; reconciliation is an **additive `ReconciliationRecord`**, never an UPDATE to the estimate; only authoritative or properly-reconciled sources count as spend (no permanent vendor estimates). Transient query states `provisional` / `estimate_only` are *display states* on aggregates, not provenance enum values.
- **Binding tier** ∈ `exact | deterministic | candidate | likely`. `candidate`/`likely` are advisory, review-queued, and **never fed to billing-grade metrics**.
- **Outcome signal class** ∈ `action_attempted | outcome_confirmed | outcome_retracted`. A 200/successful tool call is `action_attempted` unless the result is authoritative; a confirmed outcome may later flip to `outcome_retracted`, which **removes it from the cost-per-outcome denominator** and re-emits the annotated metric (never silently left).
- **Conservative propagation:** every rollup carries `minimum_tier` (the least-trusted member — the displayed label) **and** `confidence_distribution: dict[tier, int]`, both serialized on the wire/storage schema so no surface (API/notify) can silently collapse them. A property test asserts this; do not weaken it.

---

## 5. Workflow & hygiene

- **Small, reversible commits.** Conventional Commits (`feat:`, `fix:`, `test:`, `refactor:`, `chore:`). Each commit passes the full gate (pyright, ruff, tests, coverage).
- **Branch off the default branch**, never commit straight to it. PRs only.
- **Coverage gate:** core logic packages ≥ **90%** (line+branch). Projection/generated code (`apps/*` registry projections, generated clients) excluded via config. Coverage may not regress.
- **No secrets in the repo.** BYO keys live in the user's env/secret store; tests use fakes. A secret-scan runs in CI.
- **Docstrings** on every public function/class — they are also the agent-integration surface (agents read installed source). Keep them accurate; **stale docs are worse than none.**
- **Errors are typed and explicit.** No bare `except:`; catch specific exceptions; never swallow. Capture/SDK code must **never crash the host app** — the SDK fails open (logs + drops telemetry), never propagates into user code.

---

## 6. Definition of Done (a change is done only when ALL hold)

- [ ] Failing test written first; now green (red→green→refactor followed).
- [ ] Unit + integration + e2e present at the applicable levels.
- [ ] `pyright --strict` clean; `ruff check`/`format` clean (TS: `tsc`/eslint clean).
- [ ] Coverage ≥ 90% on touched core packages; no regression.
- [ ] No new type defined outside `core`; no logic→surface import; capability on all surfaces.
- [ ] Honesty-axis invariants upheld and tested where touched.
- [ ] Public API docstrings accurate; CHANGELOG/notes updated if user-facing.
- [ ] Commit messages conventional; PR description explains what + why.

If any box is unchecked, the work is not done — do not claim it is.

---

## 5a. The ratchet — every bug becomes a permanent guardrail (MANDATORY)

**A bug is never "just fixed." Fixing the instance is only step one. You must also make the entire *class* of that bug impossible — or at minimum, caught automatically — so it can never recur.** This is the single most important discipline for keeping AI-and-human-written code from drifting. The codebase only ratchets *tighter* over time, never looser.

Whenever you find a bug, a broken behavior, a type that was too loose, or any defect — **before you call it done, do ALL of these:**

1. **Write a regression test** that fails before your fix and passes after. (TDD: this comes first anyway.)
2. **Tighten the type system / lint so the class can't recur.** Ask: "what type, lint rule, or check would have made this impossible to write?" Then add it. Examples: replace a loose `str` with a `Literal`/`NewType`; make an illegal state unrepresentable (a union of valid shapes instead of a bag of optionals); add a `ruff`/pyright setting or a custom rule; narrow a return type.
3. **Add or strengthen a CONFORMANCE RULE** (see below) if the defect is an engineering-principle violation that types alone can't catch.
4. **Document the rule** in this file (§5b) so the reasoning is durable and the next contributor — human or AI — won't reintroduce it.

If a bug could only be fixed at the instance level (no test, no type, no rule prevents recurrence), say so explicitly in the PR and explain why — that is the rare exception, not the default.

## 5b. Conformance rules — custom executable checks that encode our engineering principles

Beyond `pyright` and `ruff`, this repo maintains a **conformance test suite** (`tests/conformance/`) — strong, custom, executable checks that encode our principles and the accumulated lessons from every bug we've hit. These run in CI and **block merge**. They are the institutional memory of "never write code like this again," made executable rather than aspirational.

Conformance rules we maintain (extend this list every time a new class of issue appears):

- **No type defined outside `core`** — AST/import scan; fails if a domain model is declared in a logic/app package.
- **No logic→surface import** — `capture`/`attribution`/`eval`/… must not import FastAPI/typer/the MCP SDK (import-linter contract).
- **Dependency direction** — all packages flow toward `core`; no cycles.
- **Every capability is on every surface it declares** — registry vs API/MCP/CLI projection check.
- **Honesty-axis invariants** — every cost number carries a `provenance`; every outcome→run link carries a `tier`; rollups expose `minimum_tier` + `confidence_distribution`; an estimate is never rendered as billed; reconciliation is additive, never an UPDATE. Property tests assert conservative propagation.
- **No `tiktoken` for cost** — banned import outside the explicitly-flagged fallback path.
- **Tenant scoping** — a store query without a `tenant_id` scope fails the conformance check.
- **SDK fails open** — capture/SDK code paths are asserted not to propagate exceptions into the host call path.
- **No secret logging** — provider keys/ingest keys must not reach loggers.

When you hit a bug whose class isn't yet covered, **add a conformance rule for it here and in `tests/conformance/`** as part of the same PR. A bug fix without its guardrail is incomplete.

### Test layout rule (multi-package collision avoidance — ratchet, 2026-06-27)

Because every package has a `tests/` directory, test modules MUST NOT be cross-imported by a global name:
- **Never write `from tests.conftest import ...`** (or `from tests import ...`). Under `--import-mode=importlib`, two packages' `tests.conftest` collide and break the combined repo run.
- Shared **fixtures** go in the package's `conftest.py` and are **auto-discovered** (request by parameter name) — never imported explicitly.
- Shared **constants/helpers** go in `tests/_helpers.py` and are imported with a **bare `import _helpers` / `from _helpers import ...`** — NOT `from tests._helpers import ...`. Under `--import-mode=importlib` with `consider_namespace_packages=true`, `tests` is a namespace package shared across every `packages/*/tests`, so any `tests.<x>` import collides repo-wide; a bare sibling import resolves because importlib puts the test file's own directory on `sys.path` at import time. There must be **no `tests/__init__.py`** (it would re-break this).

### Wire validation is JSON-mode, not dict-mode (ratchet, 2026-06-27)

The API projection (`apps/api`) MUST validate a request body with **JSON-mode** semantics — `input_model.model_validate_json(json.dumps(scoped))` — **never** dict-mode `model_validate(parsed_dict)`. A `StrictModel` capability input (e.g. `MetricDefinition`, which has a `tuple[str, ...]` field) rejects a Python `list` for a `tuple` in dict mode but accepts a JSON array in JSON mode; the wire payload IS JSON, so dict-mode validation made strict-input capabilities un-callable over HTTP (a `run_metric` POST 422'd on `group_by: []`). Guardrail: `apps/api/tests/test_app.py::test_tuple_field_accepts_a_json_array_on_the_wire` drives a strict tuple-field capability over the wire and fails if the projection regresses to dict-mode validation.

### Capability runtimes bind to the assembled registry, not a staging copy (ratchet, 2026-06-27)

A logic package whose capability handler closes over a late-bound runtime holder keyed by the registry object (`WeakKeyDictionary[Registry, holder]`, e.g. capture/metrics/attribution) only works if **the holder is keyed by the same `Registry` the surfaces project from**. `register_modules` therefore calls each module's `register(registry)` **directly** on the final (`_DiscoveryRegistry`) instance — never a per-module staging `Registry` whose specs are copied across (the copy would orphan the holder, so `bind_runtime(final_registry, ...)` could never reach the handler's holder). The one documented duplicate name (`validate_outcome_rule`) is skipped by `_DiscoveryRegistry.register`, preserving the no-silent-overwrite contract. Guardrail: `apps/server/tests/test_e2e.py::test_ingested_span_persists_and_is_queryable` boots the full assembly and fails if a wired runtime is unreachable; `apps/agent_integrability/tests/test_discovery.py` keeps the dedup + collision contract.

### The metric executor must honour every grammar dimension (ratchet, 2026-06-27)

The metric `group_by` allowlist (`valuemaxx.metrics.grammar.Dimension`) and the executor's grouping (`valuemaxx.metrics.executor`) must **not drift**. A dimension the DSL accepts but the executor does not resolve gets **silently dropped** — `_cost_group_key`/`_outcome_group_key` return an empty key, so the grouped query collapses into one ungrouped total and a per-`agent_name` (or per-`tenant`) rollup renders as a single misleading number. This was real: `agent_name` and `tenant` were valid `Dimension` members but unhandled by the executor, so `group_by=("agent_name",)` returned an ungrouped cell instead of one cost cell per agent. Cost-by-agent additionally requires a **run join** (a `CostEvent` carries no agent — agent lives on `Run`), so the executor takes an optional `RunRepository` and resolves `run_id → Run.agent_name`, bucketing a missing/agent-less run under `"unknown"` (never dropping the dimension); the server wires `bridge.runs` into `MetricExecutor`. Guardrail: `valuemaxx.metrics.executor.handled_dimensions()` exposes the executor's resolved set and `packages/metrics/tests/test_executor.py::test_every_grammar_dimension_is_handled_by_the_executor` fails if it ever stops equalling `set(Dimension)` — adding a `Dimension` without wiring it in breaks the build. `apps/server/tests/test_rollup_integration.py` proves cost-by-model, cost-by-agent (run join), and cost-per-outcome rollups against a temp-SQLite store carry both H7 fields.

## 6a. Parallel execution (for orchestrating agents)

When implementing this project, **parallelize aggressively**: most packages and most tasks within a package are independent and should be built concurrently by subagents, not serially.

- **Fan out independent work.** Packages with no dependency on each other (e.g. `capture`, `outcomes`, `reconciliation`, `allocation`, `eval`, `metrics` once `core` exists) are built in parallel by separate subagents. Within a package, independent modules/tests parallelize too.
- **Respect the dependency order.** `core` (the typed spine) and `capabilities` (the registry contract) are built **first and alone** — everything imports them, so they're the serialization point. After they're locked, fan out.
- **Each parallel task is self-contained and TDD'd** — a subagent owns a package/module end to end (failing tests → implementation → green → typed → covered), then reports back. Tasks that mutate files concurrently must run in isolated git worktrees to avoid conflicts.
- **Integration is the barrier.** After parallel package work completes, a serial integration + e2e pass wires them and runs cross-package tests against real Postgres.
- **Use the available orchestration skills** for this — `superpowers:subagent-driven-development` and `superpowers:dispatching-parallel-agents` for fan-out, `azath-workflows:coordinator-subagent-workflow` for plan-driven dispatch-review-loop execution, and the `Workflow` tool for deterministic parallel pipelines. The implementation plan marks each task with a parallelization group so the coordinator knows what can run together.

## 7. For AI agents specifically

- **Read this file and `CLAUDE.md` before writing code.** Re-read when unsure.
- **Do not invent APIs.** If a function/library/flag isn't confirmed to exist, check the installed source or docs; never hallucinate a signature.
- **Follow the existing patterns** in the package you're editing — match its idiom, naming, and structure.
- **When a task is ambiguous, ask** rather than guess. A wrong-but-plausible implementation is worse than a question.
- **Never weaken a test, a type, or an honesty invariant to make something pass.** If it doesn't pass honestly, it isn't done.
