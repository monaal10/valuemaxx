# Releasing valuemaxx

valuemaxx ships **two published packages in lockstep**: the Python SDK (PyPI: `valuemaxx`) and the TypeScript SDK (npm: `valuemaxx`). One git tag publishes both at the **same version**. Everything else in the monorepo (`packages/*`, `apps/*`) is internal and never published.

## Why this setup (and not changesets / release-please)

We publish exactly **2 packages, lockstep**. The standard release tools (changesets, release-please, semantic-release) exist to coordinate *many* packages with *independent* versions — complexity we don't have. changesets is JS-only (would need a `pyproject.toml` hack for our Python side); release-please needs a verbose manifest + conventional commits. For 2 lockstep packages, a single `VERSION` file + a stamp script + a tag-triggered workflow is the lower-risk, lower-maintenance choice — it's essentially what those tools generate internally, minus the framework. (This is the Sentry `craft` + `bump-version.sh` pattern, scaled down.)

> Note: most dual-language projects (Sentry, PostHog, LangChain, Supabase) actually keep Python and JS in *separate repos with independent versions*. True cross-language lockstep is uncommon outside codegen'd SDKs (AWS CDK/jsii). We lockstep deliberately, as a product decision — "one valuemaxx vX.Y.Z release surface." Revisit if we ever publish several independently-versioned packages.

## The single source of version truth

**`VERSION`** (repo root) is the one place the published version lives. `scripts/stamp_version.py` is the **only** thing that writes the version into the two SDK manifests:
- `sdks/python/pyproject.toml` → `project.version`
- `sdks/typescript/package.json` → `version`

CI runs `python scripts/stamp_version.py --check` on every push, so the manifests can never silently drift from `VERSION`.

Internal packages are **enforced unpublishable**, not by discipline:
- Python: each carries the `Private :: Do Not Upload` classifier — PyPI/Warehouse *rejects* any upload with it.
- npm: internal/root `package.json` set `"private": true` — npm refuses to publish.

## Cutting a release

1. **Bump `VERSION`** to the new semver (e.g. `0.1.0`) in a **reviewed PR**. (This PR *is* your explicit, reviewable release intent — the human gate a release-PR bot would otherwise provide.) Run `python scripts/stamp_version.py` locally so the manifests are stamped in the same PR; CI's `--check` enforces it.
2. **Merge** the PR.
3. **Tag and push:**
   ```bash
   git tag v0.1.0
   git push origin v0.1.0
   ```
4. `.github/workflows/release.yml` fires on the `v*` tag:
   - **gate** — the full suite (ruff, pyright, lint-imports, pytest+coverage, conformance) must pass, and the tag must match `VERSION`.
   - **publish-python** — builds the Python SDK and publishes to PyPI via **trusted publishing (OIDC)** — no stored token.
   - **publish-npm** — builds/tests the TS SDK and publishes to npm via **OIDC trusted publishing** (provenance attestations emitted by default) — no stored token.

Both publish jobs run only after `gate` is green, so a release can never ship red.

## One-time setup before the first real publish

- **PyPI:** configure a [Trusted Publisher](https://docs.pypi.org/trusted-publishers/) for `valuemaxx` pointing at this repo + the `release.yml` workflow + the `pypi` environment.
- **npm:** configure [trusted publishing (OIDC)](https://docs.npmjs.com/trusted-publishers) for `valuemaxx` pointing at this repo + `release.yml` + the `npm` environment. Requires a **public repo + public package** and a **GitHub-hosted runner** (OIDC isn't supported on self-hosted runners). npm CLI ≥ 11.5.1 (the workflow upgrades it).
- **Delete any stored `PYPI_TOKEN` / `NPM_TOKEN` secrets** — OIDC replaces them, and long-lived tokens are the primary CI supply-chain risk (cf. the March 2025 litellm token-theft incident).

## Pre-1.0

While `VERSION` is `0.x`, the public API may change between minors. The lockstep guarantee still holds: pip `valuemaxx` and npm `valuemaxx` always share the version on `VERSION`.
