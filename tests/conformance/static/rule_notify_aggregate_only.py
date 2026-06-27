"""notify_aggregate_only — a digest model must hold no raw-content / PII field.

A digest model is aggregate-only: it may never declare a field whose name reads as
raw model content or PII (prompt/response/raw/email/customer_id/user_id/...). The
``flags_violation`` check inspects a pydantic model class for such a field (and
still flags the legacy source-string negative fixture). The foundation subject is
the real :class:`~valuemaxx.notify.models.DigestMetric`, which carries only
aggregates plus its H7 confidence.

NOTIFY turns this rule green by shipping aggregate-only digest models guarded by an
``extra="forbid"`` config AND a field-name denylist validator (a second backstop so
a future author cannot add a raw field and have it silently ship).
"""

from __future__ import annotations

from pydantic import BaseModel

from tests.conformance.rulebase import Rule, RuleKind

# Field-name fragments that read as raw model content or PII. Substring match.
_FORBIDDEN_FIELD_MARKERS: tuple[str, ...] = (
    "raw",
    "prompt",
    "response",
    "email",
    "customer_id",
    "user_id",
    "pii",
    "content",
)

# The legacy source-string markers (kept so the synthetic negative fixture flags).
_SOURCE_MARKERS: tuple[str, ...] = ("raw_prompt", "end_user_email", "raw_response")


def _has_forbidden_field(model: type[BaseModel]) -> bool:
    return any(
        any(marker in name.lower() for marker in _FORBIDDEN_FIELD_MARKERS)
        for name in model.model_fields
    )


def _flags(subject: object) -> bool:
    # The harness passes either a model class (the real/foundation subject) or the
    # raw source string of a synthetic violation — accept both.
    if isinstance(subject, type) and issubclass(subject, BaseModel):
        return _has_forbidden_field(subject)
    assert isinstance(subject, str)
    return any(marker in subject for marker in _SOURCE_MARKERS)


class _LeakyDigest(BaseModel):
    raw_prompt: str
    end_user_email: str


def _negative_fixture() -> object:
    return _LeakyDigest


def _foundation_subject() -> object:
    from valuemaxx.notify.models import DigestMetric

    return DigestMetric


RULE = Rule(
    name="notify_aggregate_only",
    kind=RuleKind.STATIC,
    green_now=True,
    owner_task="NOTIFY",
    flags_violation=_flags,
    negative_fixture=_negative_fixture,
    foundation_subject=_foundation_subject,
)
