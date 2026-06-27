# CLAUDE.md

This file guides Claude Code (and other AI coding agents) working in this repository.

## Read this first

**The engineering standards are in [`AGENTS.md`](./AGENTS.md). Read it fully before writing any code. It is binding and overrides any default behavior or habit.**

The short version of the non-negotiables (full detail in AGENTS.md):

1. **TDD always** — failing test first, then code. Red → Green → Refactor. Unit + integration + e2e at every applicable stage.
2. **Strict typing** — `pyright --strict` + `ruff` clean before any commit. No `Any` on public surfaces, no unjustified `# type: ignore`. Pydantic v2 at boundaries. TS SDK: `tsconfig` strict.
3. **No duplication** — domain types live only in `packages/core`; everything imports from it.
4. **The three honesty axes are tested invariants** — cost provenance (`measured|estimated|allocated|provider_reconciled|manual_reconciled`), binding tier (`exact|deterministic|candidate|likely`), outcome signal class (`action_attempted|outcome_confirmed|outcome_retracted`). (Eval `reliable`/`directional` is a per-recommendation label in the eval package, NOT a system axis.) Never launder one upward; rollups carry `minimum_tier` + `confidence_distribution`.
5. **Surfaces are projections** — API/MCP/CLI are generated from the capability registry; never hand-write a capability into one surface.
6. **Coverage ≥ 90% on core** packages; never regress.
7. **The ratchet (AGENTS.md §5a/§5b)** — every bug becomes a permanent guardrail: regression test + tightened type/lint + a **conformance rule** (`tests/conformance/`) + a documented rule, so its *class* can never recur. The codebase only ratchets tighter. A bug fix without its guardrail is incomplete.

## What this project is

An open-source **AI margin intelligence** tool: it captures correct, reconciled LLM cost per agent run, joins it to the **user-defined business outcome** each run produced (with a confidence tier), and recommends cheaper/faster models that hold that outcome — for teams that **build** AI agents. See `docs/plans/` for the design and implementation plan.

## Project layout (monorepo, uv workspace)

- `packages/core` — typed spine (pydantic v2 models). **Only place types are defined.**
- `packages/capabilities` — single-source-of-truth operation registry; API/MCP/CLI project from it.
- `packages/capture`, `outcomes`, `attribution`, `reconciliation`, `allocation`, `metrics`, `eval`, `onboarding`, `store` — logic packages (no surface imports).
- `apps/api|mcp|cli|notify` — thin projections / sinks.
- `sdks/python`, `sdks/typescript` — thin `init()` producers over OTLP.

## Commands (run before claiming done)

```bash
uv run pyright            # strict type gate — must be clean
uv run ruff check .       # lint — must be clean
uv run ruff format .      # format
uv run pytest             # all tests; coverage gate enforced in CI
```
(Exact commands are defined in `pyproject.toml` / CI; prefer those if they differ.)

## Working rules for agents

- **Read `AGENTS.md` and the relevant design/impl-plan section before coding.** Don't start from memory.
- **Don't invent APIs/signatures** — verify against installed source or docs.
- **Match the existing package's patterns.** Reuse over invention; keep changes small and reversible.
- **Never weaken a test, type, or honesty invariant to make something pass.** If it doesn't pass honestly, it isn't done.
- **The SDK must fail open** — capture/instrumentation must never crash or slow the host app.
- **When ambiguous, ask.** A wrong-but-plausible change is worse than a question.

## Parallel execution

When implementing, **parallelize independent work across subagents** — don't build serially. Build `core` and `capabilities` first (everything depends on them), then fan out independent packages (`capture`, `outcomes`, `reconciliation`, `allocation`, `eval`, `metrics`, …) concurrently, each owned end-to-end by a subagent with full TDD, then do a serial integration + e2e pass. Use `superpowers:subagent-driven-development` / `superpowers:dispatching-parallel-agents` / `azath-workflows:coordinator-subagent-workflow` and the `Workflow` tool. Concurrent file-mutating tasks run in isolated git worktrees. The implementation plan marks each task's parallelization group. See `AGENTS.md` §6a.
