"""The SINGLE source of truth for onboarding SCAN detection rules (cross-language).

The scanner looks for the same things in Python and TypeScript source. Those detection
rules — which call names are LLM run boundaries, which are provider setups, which method
names are ORM writes, the outcome-transition name stems, the source-file extensions, the
directories to skip, and the echoing/external outcome systems — are declared here ONCE
and serialized to ``tests/wire_contract/onboarding_rules.json`` by
:func:`generate_onboarding_rules_fixture`. The Python scanner reads these constants
directly; the TypeScript scanner reads the generated JSON. CI regenerates the fixture and
``git diff --exit-code``s it, so a change to a rule here that isn't reflected in the
committed fixture (which the TS side consumes) fails the build — the two scanners can
never silently drift.

Only the drift-prone *data* (the rule sets) lives here. The scanning *mechanics* (AST
walking, redaction, file iteration) are small and idiomatic per language, and are kept in
parity by a golden test that runs a fixture repo through both pipelines.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from pathlib import Path

# TS/JS call names that mark an LLM run boundary (the Vercel AI SDK verbs).
TS_LLM_CALLS: Final[tuple[str, ...]] = (
    "generateText",
    "streamText",
    "generateObject",
    "streamObject",
    "embed",
)
# Provider-setup calls that also mark a run boundary (model construction).
TS_PROVIDER_CALLS: Final[tuple[str, ...]] = (
    "createOpenAI",
    "createAnthropic",
    "createGoogleGenerativeAI",
    "createGateway",
)
# Method names that mark a database write (outcome sites).
ORM_WRITES: Final[tuple[str, ...]] = (
    "save",
    "update",
    "insert",
    "create",
    "upsert",
    "delete",
)
# Function/method-name stems that signal an outcome transition.
#
# These are matched as a *verb followed by an object* (``markCompleted``, ``mark_completed``)
# — never as a bare verb, and never as a longer lowercase word that merely starts with one.
# See ``MARK_REQUIRES_OBJECT_SUFFIX``: without that rule, ``close()`` on a DB lease,
# ``resolve()`` on a Promise, and the noun ``marker``/``markdown`` all register as CONFIRMED
# business outcomes. On a real repo that was ~1,045 matches, of which ~880 were noise.
#
# ``resolve`` is deliberately ABSENT for TS/JS: there it overwhelmingly means "look up"
# (``resolveGatewayUrl``, ``resolveModelRuntimeConfig``) or Promise settlement, not "resolve a
# ticket". The Python-AST scanner keeps its own ``resolve`` stem (see ``scan.py``), where the
# SQLAlchemy/Django idiom does carry the outcome meaning.
MARK_PREFIXES: Final[tuple[str, ...]] = (
    "mark",
    "close",
    "complete",
    "finalize",
)
# An outcome-transition name must continue past the stem with an uppercase letter or an
# underscore (``markCompleted`` / ``mark_completed``). A bare stem (``close()``) or a
# lowercase continuation (``marker``, ``closed``, ``markdown``) is NOT an outcome.
MARK_REQUIRES_OBJECT_SUFFIX: Final[bool] = True

# TS/JS source file extensions the scanner parses.
TS_SUFFIXES: Final[tuple[str, ...]] = (".ts", ".tsx", ".js", ".mjs", ".cjs", ".jsx")

# Systems whose outbound calls, when they carry a run id, echo it back on a later webhook
# (so binding is deterministic). A subset of EXTERNAL_SYSTEMS.
ECHOING_SYSTEMS: Final[tuple[str, ...]] = ("stripe", "hubspot", "zendesk")

# Outbound systems whose calls are outcome-bearing external writes (receiver -> canonical
# system name recorded on the site). Includes the echoing systems plus non-echoing ones.
EXTERNAL_SYSTEMS: Final[dict[str, str]] = {
    "stripe": "stripe",
    "hubspot": "hubspot",
    "zendesk": "zendesk",
    "salesforce": "salesforce",
    "sendgrid": "sendgrid",
    "twilio": "twilio",
    "calendar": "calendar",
}

# Directories the scanner never descends into (plus any dot-directory).
IGNORED_DIRS: Final[tuple[str, ...]] = (
    "node_modules",
    ".git",
    ".worktrees",
    ".claude",
    ".codex",
    ".cursor",
    ".stellar",
    "dist",
    "build",
    ".next",
    ".nuxt",
    ".venv",
    "venv",
    "__pycache__",
    "coverage",
    ".wrangler",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tmp",
    "vendor",
    "target",
)

# Directories whose contents are tests/fixtures, never production outcome sites.
# A test file's `markCompleted()` is a fake, and proposing a rule against it would bind
# real production cost to an assertion. Scanned repos are typically 50-65% test code, so
# this is also the single largest noise reduction in the scan.
IGNORED_TEST_DIRS: Final[tuple[str, ...]] = (
    "tests",
    "test",
    "__tests__",
    "e2e",
    "fixtures",
    "__fixtures__",
    "__mocks__",
    "testdata",
)

# Filename infixes that mark a test/fixture/mock module (checked against the file STEM, so
# `client.test.ts` and `agent.spec.tsx` match while `latest.ts` does not).
IGNORED_FILE_INFIXES: Final[tuple[str, ...]] = (
    ".test",
    ".spec",
    "_test",
    "_spec",
    ".fixture",
    ".mock",
    ".stories",
)

# The symbol recorded when a site is not inside any named function (module scope). Such a
# site is NOT proposable: the SDK instruments a named function at init(), so a rule targeting
# module scope can never bind. `propose` drops these.
MODULE_SYMBOL: Final[str] = "<module>"

# Identifiers that look like entity ids but are excluded (not real entity keys).
ENTITY_ID_EXCLUSIONS: Final[tuple[str, ...]] = ("uuid", "guid")

# The placeholder every redacted secret is replaced with (both languages).
REDACTION_PLACEHOLDER: Final[str] = "[REDACTED]"

# Secret-shaped token patterns (as regex SOURCE strings so both Python `re` and JS RegExp
# consume the identical patterns). Order matters: the admin key pattern is first so it wins
# over the generic sk-ant one. Kept ASCII/portable so the two engines agree.
REDACT_PREFIX_PATTERNS: Final[tuple[str, ...]] = (
    r"sk-ant-admin\d{2}-[A-Za-z0-9_-]{6,}",  # Anthropic admin key
    r"sk-ant-[A-Za-z0-9_-]{6,}",  # Anthropic API key
    r"sk-[A-Za-z0-9_-]{16,}",  # OpenAI-style API key
    r"AKIA[0-9A-Z]{16}",  # AWS access key id
    r"Bearer\s+[A-Za-z0-9._\-]{16,}",  # Authorization bearer token
)
# The secret-named-identifier alternation used in the assignment-form pattern.
REDACT_SECRET_NAME_ALT: Final[str] = (
    r"api[_-]?key|secret|password|passwd|token"
    r"|auth[_-]?token|access[_-]?key|client[_-]?secret"
)
# High-entropy blob detection: a long unbroken credential-ish run, scrubbed only if its
# Shannon entropy (bits/char) meets the threshold (so real prose/code is never scrubbed).
#
# `/` is deliberately EXCLUDED from the character class. With it, a long file path is one
# unbroken 40+ char run — `src/workflows/complete-submission/steps/capture-and-store/index`
# scores 4.16 bits and was scrubbed to `[REDACTED]`, destroying the `match_target` of every
# rule in a deeply-nested repo (1,554 rules on one real scan). Entropy alone cannot separate
# these: English prose and kebab-case paths both sit near 4.0-4.5 bits, ABOVE the threshold.
# Excluding the path separator is what makes a path decompose into short segments that never
# reach the 40-char minimum, while real secrets (`sk-ant-…`, `ghp_…`, base64 blobs) still
# match as one run. AWS keys and JWTs are covered by REDACT_PREFIX_PATTERNS regardless.
REDACT_HIGH_ENTROPY_PATTERN: Final[str] = r"[A-Za-z0-9+=_-]{40,}"
REDACT_HIGH_ENTROPY_BITS: Final[float] = 3.5


def is_outcome_transition_name(name: str, prefixes: tuple[str, ...] = MARK_PREFIXES) -> bool:
    """Return True iff ``name`` reads as a *verb + object* outcome transition.

    ``markCompleted`` / ``mark_completed`` -> True. A bare stem (``close``) or a lowercase
    continuation (``marker``, ``closed``, ``markdown``, ``completes``) -> False: those are a
    DB-lease close, a Promise settle, or a noun that merely starts with the stem, and
    labeling them CONFIRMED outcomes is exactly the honesty violation the tiers exist to
    prevent. Mirrored in TS by ``isOutcomeTransitionName`` in ``scan.ts``.
    """
    low = name.lower()
    for prefix in prefixes:
        if not low.startswith(prefix):
            continue
        rest = name[len(prefix) :]
        if not rest:
            return False  # bare verb: close(), resolve()
        if not MARK_REQUIRES_OBJECT_SUFFIX:
            return True
        if rest[0] == "_" or rest[0].isupper():
            return True
    return False


def is_test_path(relative_path: str) -> bool:
    """Return True iff ``relative_path`` is test/fixture/mock code (never an outcome site).

    Matches a path SEGMENT against :data:`IGNORED_TEST_DIRS` and the filename STEM against
    :data:`IGNORED_FILE_INFIXES` (so ``client.test.ts`` matches but ``latest.ts`` does not).
    Mirrored in TS by ``isTestPath`` in ``onboard.ts``.
    """
    normalized = relative_path.replace("\\", "/")
    segments = normalized.split("/")
    if any(segment in IGNORED_TEST_DIRS for segment in segments[:-1]):
        return True
    filename = segments[-1]
    stem = filename.split(".")[0] if filename.startswith(".") else filename
    # Strip only the final extension so `.test` in `client.test.ts` remains visible.
    dot = stem.rfind(".")
    if dot > 0:
        stem = stem[:dot]
    return any(infix in stem for infix in IGNORED_FILE_INFIXES)


def as_dict() -> dict[str, object]:
    """The full rule set as a JSON-serializable dict (the cross-language contract).

    Lists are sorted where order does not matter (so the fixture is stable regardless of
    source declaration order); ``EXTERNAL_SYSTEMS`` keeps its mapping.
    """
    return {
        "ts_llm_calls": sorted(TS_LLM_CALLS),
        "ts_provider_calls": sorted(TS_PROVIDER_CALLS),
        "orm_writes": sorted(ORM_WRITES),
        "mark_prefixes": sorted(MARK_PREFIXES),
        "mark_requires_object_suffix": MARK_REQUIRES_OBJECT_SUFFIX,
        "ts_suffixes": sorted(TS_SUFFIXES),
        "echoing_systems": sorted(ECHOING_SYSTEMS),
        "external_systems": dict(sorted(EXTERNAL_SYSTEMS.items())),
        "ignored_dirs": sorted(IGNORED_DIRS),
        "ignored_test_dirs": sorted(IGNORED_TEST_DIRS),
        "ignored_file_infixes": sorted(IGNORED_FILE_INFIXES),
        "entity_id_exclusions": sorted(ENTITY_ID_EXCLUSIONS),
        "module_symbol": MODULE_SYMBOL,
        "redaction_placeholder": REDACTION_PLACEHOLDER,
        # Redaction patterns keep source ORDER (the admin-key pattern must precede the
        # generic sk-ant one), so they are NOT sorted.
        "redact_prefix_patterns": list(REDACT_PREFIX_PATTERNS),
        "redact_secret_name_alt": REDACT_SECRET_NAME_ALT,
        "redact_high_entropy_pattern": REDACT_HIGH_ENTROPY_PATTERN,
        "redact_high_entropy_bits": REDACT_HIGH_ENTROPY_BITS,
    }


def generate_onboarding_rules_fixture(path: Path) -> None:
    """Write the cross-language rules fixture (``{...}`` from :func:`as_dict`) to ``path``.

    CI regenerates this and runs ``git diff --exit-code`` so a rule change here that is not
    reflected in the committed fixture (and thus the TS scanner) fails the build.
    """
    path.write_text(json.dumps(as_dict(), indent=2, sort_keys=True) + "\n")


__all__ = [
    "ECHOING_SYSTEMS",
    "ENTITY_ID_EXCLUSIONS",
    "EXTERNAL_SYSTEMS",
    "IGNORED_DIRS",
    "IGNORED_FILE_INFIXES",
    "IGNORED_TEST_DIRS",
    "MARK_PREFIXES",
    "MARK_REQUIRES_OBJECT_SUFFIX",
    "MODULE_SYMBOL",
    "ORM_WRITES",
    "REDACTION_PLACEHOLDER",
    "REDACT_HIGH_ENTROPY_BITS",
    "REDACT_HIGH_ENTROPY_PATTERN",
    "REDACT_PREFIX_PATTERNS",
    "REDACT_SECRET_NAME_ALT",
    "TS_LLM_CALLS",
    "TS_PROVIDER_CALLS",
    "TS_SUFFIXES",
    "as_dict",
    "generate_onboarding_rules_fixture",
]
