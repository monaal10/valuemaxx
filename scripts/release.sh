#!/usr/bin/env bash
#
# Cut a valuemaxx release: bump VERSION, stamp both SDK manifests, run the full local
# gate, commit, and tag — one command. Pushing the tag triggers the release workflow,
# which publishes pip `valuemaxx` + npm `valuemaxx` at the same version via OIDC.
#
#   scripts/release.sh 0.2.0
#
# Publishing is PERMANENT (a version can never be re-uploaded to PyPI/npm), so this
# script is deliberately cautious: it refuses on a dirty tree, a non-semver or
# already-published version, or a failing local gate, and asks for an explicit "yes"
# before it commits/tags. It does NOT push by default — it prints the exact push
# command so the actual publish is a separate, conscious step (pass --push to push
# automatically). See RELEASING.md.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# --- args -------------------------------------------------------------------------------
PUSH=0
VERSION=""
for arg in "$@"; do
  case "$arg" in
    --push) PUSH=1 ;;
    -*) echo "error: unknown flag '$arg'" >&2; exit 2 ;;
    *) if [ -n "$VERSION" ]; then echo "error: version given twice" >&2; exit 2; fi; VERSION="$arg" ;;
  esac
done

if [ -z "$VERSION" ]; then
  echo "usage: scripts/release.sh <version> [--push]" >&2
  echo "  e.g. scripts/release.sh 0.2.0" >&2
  exit 2
fi
VERSION="${VERSION#v}"  # tolerate a leading v

RELEASE_BRANCH="main"
TAG="v${VERSION}"

step() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }
fail() { printf '\033[31merror: %s\033[0m\n' "$1" >&2; exit 1; }

# --- preflight checks -------------------------------------------------------------------
step "Preflight"

# Semver (x.y.z with an optional -prerelease); the stamp script also enforces this.
if ! printf '%s' "$VERSION" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$'; then
  fail "'$VERSION' is not a semantic version (expected x.y.z)"
fi

# Clean working tree — never tag a release on top of uncommitted changes.
if [ -n "$(git status --porcelain)" ]; then
  fail "working tree is dirty; commit or stash first (a release must be reproducible)"
fi

# The tag must not already exist locally or on the remote.
if git rev-parse -q --verify "refs/tags/${TAG}" >/dev/null; then
  fail "tag ${TAG} already exists locally"
fi
if git ls-remote --exit-code --tags origin "${TAG}" >/dev/null 2>&1; then
  fail "tag ${TAG} already exists on origin (this version was already released)"
fi

# The version must be NEW on both registries (a published version can't be re-uploaded).
if command -v npm >/dev/null 2>&1 && npm view "valuemaxx@${VERSION}" version >/dev/null 2>&1; then
  fail "valuemaxx@${VERSION} is already on npm — pick a new version"
fi
if command -v curl >/dev/null 2>&1 && \
   curl -sf "https://pypi.org/pypi/valuemaxx/${VERSION}/json" >/dev/null 2>&1; then
  fail "valuemaxx ${VERSION} is already on PyPI — pick a new version"
fi

CURRENT="$(cat VERSION 2>/dev/null || echo '?')"
echo "  current VERSION : ${CURRENT}"
echo "  releasing       : ${VERSION}  (tag ${TAG} on ${RELEASE_BRANCH})"

# --- bump + stamp -----------------------------------------------------------------------
step "Bumping VERSION and stamping both SDK manifests"
printf '%s\n' "$VERSION" > VERSION
uv run python scripts/stamp_version.py "$VERSION"
uv run python scripts/stamp_version.py --check   # belt-and-suspenders: manifests match

# --- local gate (do not tag a release that would fail CI) -------------------------------
step "Running the local gate (same checks the release workflow gates on)"
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run lint-imports
uv run python scripts/bundle_for_release.py --check   # the release-only bundle isn't committed
uv run pytest -q

# --- confirm ----------------------------------------------------------------------------
step "Ready to commit + tag ${TAG}"
git --no-pager diff --stat VERSION sdks/python/pyproject.toml sdks/typescript/package.json
printf '\nThis will commit the bump and create tag %s. Pushing the tag PUBLISHES ' "$TAG"
printf 'valuemaxx %s to PyPI + npm (permanent).\nProceed? [y/N] ' "$VERSION"
read -r reply
case "$reply" in
  y|Y|yes|YES) ;;
  *) step "Aborted — reverting the version bump"; git checkout -- VERSION sdks/python/pyproject.toml sdks/typescript/package.json; exit 1 ;;
esac

# --- commit + tag -----------------------------------------------------------------------
step "Committing + tagging"
git add VERSION sdks/python/pyproject.toml sdks/typescript/package.json
git commit -m "release: valuemaxx ${VERSION}"
git tag -a "${TAG}" -m "valuemaxx ${VERSION}"

if [ "$PUSH" -eq 1 ]; then
  step "Pushing ${RELEASE_BRANCH} + ${TAG} (triggers the release workflow)"
  git push origin "HEAD:${RELEASE_BRANCH}"
  git push origin "${TAG}"
  echo "  Release workflow: https://github.com/monaal10/valuemaxx/actions/workflows/release.yml"
else
  step "Done — nothing pushed yet"
  cat <<EOF
  Review the commit + tag, then push to publish:

      git push origin HEAD:${RELEASE_BRANCH}
      git push origin ${TAG}

  The ${TAG} tag triggers the release workflow (gate -> publish PyPI + npm via OIDC).
  Watch: https://github.com/monaal10/valuemaxx/actions/workflows/release.yml
EOF
fi
