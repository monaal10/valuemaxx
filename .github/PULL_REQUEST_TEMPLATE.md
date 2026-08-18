## What and why

<!-- The diff shows what changed. Say why it needed to. -->

## If this changes a number

<!-- Skip if it does not. If it does: which number, was it wrong before or is it wrong
now differently, and what proves the new one? -->

## Checklist

- [ ] Tests added, and they **failed for the right reason** before the fix
- [ ] `uv run ruff check . && uv run ruff format --check .`
- [ ] `uv run pyright` — 0 errors
- [ ] `uv run pytest --cov --cov-fail-under=90` and `uv run pytest tests/conformance`
- [ ] Generated files regenerated, not hand-edited (`llms.txt`, wire-parity fixtures)
- [ ] Docs updated in the same PR if this makes any of them wrong
