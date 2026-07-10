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
MARK_PREFIXES: Final[tuple[str, ...]] = (
    "mark",
    "resolve",
    "close",
    "complete",
    "finalize",
)
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
REDACT_HIGH_ENTROPY_PATTERN: Final[str] = r"[A-Za-z0-9+/=_-]{40,}"
REDACT_HIGH_ENTROPY_BITS: Final[float] = 3.5


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
        "ts_suffixes": sorted(TS_SUFFIXES),
        "echoing_systems": sorted(ECHOING_SYSTEMS),
        "external_systems": dict(sorted(EXTERNAL_SYSTEMS.items())),
        "ignored_dirs": sorted(IGNORED_DIRS),
        "entity_id_exclusions": sorted(ENTITY_ID_EXCLUSIONS),
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
    "MARK_PREFIXES",
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
