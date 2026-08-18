# Contributing to valuemaxx

Thanks for looking. This is a small project with strong opinions about honesty in
numbers, so this file is mostly about *why* the rules are what they are.

## The one idea to hold on to

valuemaxx reports what an AI outcome costs **and how much to trust that figure**. Every
number carries system-owned labels — a cost provenance, a binding tier, a signal class,
a causal-evidence level — and a caller may never set them. A caller states what
happened; it never states how much to trust the link.

Most review comments here trace back to that. A change that makes a number *look*
better by making it less honest will be declined even when the code is good.

## Getting set up

```bash
git clone https://github.com/monaal10/valuemaxx && cd valuemaxx
uv sync --all-packages --all-extras --dev     # Python side
cd sdks/typescript && npm install             # TypeScript side
```

Run the backend locally:

```bash
uv run valuemaxx up          # http://localhost:8000, dashboard at /
```

## Before you open a PR

Run what CI runs. It is fast (well under a minute) and it is the whole gate:

```bash
uv run ruff check . && uv run ruff format --check .
uv run pyright                       # strict; 0 errors required
uv run lint-imports                  # layering contracts
uv run pytest --cov --cov-fail-under=90
uv run pytest tests/conformance      # repo invariants
```

Two more that catch the mistakes people actually make here:

```bash
# Generated files must not drift. llms.txt is GENERATED from the capability
# registry — edit apps/agent_integrability/.../llms_txt.py, never llms.txt itself.
uv run python scripts/generate_llms_txt.py && git diff --exit-code llms.txt

# The wire contract is shared across two languages. Adding a semconv key means
# adding it to ALL_KEYS on the Python side AND the TS copy, or parity fails.
for f in tests/wire_contract/generate_*.py; do uv run python "$f"; done
git diff --exit-code
```

If you touched TypeScript:

```bash
(cd sdks/typescript && npm test && npx tsc --noEmit)
(cd gateway && npx vitest run && npx tsc --noEmit)
```

## House style

- **Tests first, and make sure they fail for the right reason.** A test that passes
  before the implementation exists is testing nothing. This has bitten us repeatedly:
  a route that silently dropped a field still made its tests green.
- **Comment the invisible constraint, not the code.** Say what breaks without this line.
  If the comment restates the syntax, delete it.
- **Absent is not zero.** "No data yet" and "zero" are different facts. Rendering the
  first as the second is the exact dishonesty the tier system exists to prevent.
- **Degrade, don't fabricate.** When something cannot be computed honestly, return
  `None` with a reason. Never a plausible-looking number.

## Where things live

| Path | What it is |
|---|---|
| `gateway/` | The observe-only proxy (Cloudflare Worker; deployed, not published) |
| `apps/api`, `apps/server` | The backend — routes, dashboard, composition root |
| `packages/attribution` | The binding cascade (T1–T5) — outcome ↔ run |
| `packages/metrics` | The metric DSL, executor, honesty propagation |
| `packages/eval` | Replay grading, savings, the optimization verdict |
| `packages/store` | Persistence; every method tenant-scoped |
| `sdks/{python,typescript}` | The published compat SDKs |

## Commits and releases

Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`).
Explain **why** in the body — the diff already shows what.

Releases are lockstep across pip and npm from a single `VERSION` file. See
[RELEASING.md](./RELEASING.md).

## Security

Please don't file security problems as public issues — see [SECURITY.md](./SECURITY.md).
