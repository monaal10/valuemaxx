"""no_secret_logging — a sentinel key must never reach a log/span/DB (RED; owner OUTCOMES).

Runtime sentinel rule (NOT a static grep): a known ingest/provider key is injected,
the paths are exercised, and the rule asserts the sentinel appears in no log record,
no span attribute, and no DB row. ``flags_violation`` inspects a captured-sink dump
(a list of emitted strings) and flags it iff the sentinel leaked.

Authored RED-but-meaningful: the negative fixture is a sink dump that DID leak the
sentinel. The foundation assertion is skip-marked until the owning packages run the
sentinel through their real paths.
"""

from __future__ import annotations

from typing import cast

from tests.conformance.rulebase import Rule, RuleKind

SENTINEL = "sk-ant-SENTINEL-do-not-log-0xDEADBEEF"


def _flags(subject: object) -> bool:
    """subject is the captured sink dump (emitted log/span/db strings)."""
    assert isinstance(subject, list)
    records = cast("list[object]", subject)
    return any(SENTINEL in str(record) for record in records)


def _negative_fixture() -> object:
    # a sink dump where a code path leaked the sentinel into a log line
    return [f"INFO using provider key {SENTINEL}", "DEBUG request sent"]


RULE = Rule(
    name="no_secret_logging",
    kind=RuleKind.BEHAVIORAL,
    green_now=False,
    owner_task="OUTCOMES",  # also RECON, EVAL, ONBOARDING; final at G5
    flags_violation=_flags,
    negative_fixture=_negative_fixture,
    foundation_subject=None,
)
