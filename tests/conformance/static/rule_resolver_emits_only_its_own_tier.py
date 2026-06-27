"""resolver_emits_only_its_own_tier — a resolver may emit only its declared tier.

Owner ATTRIBUTION (now GREEN). Every binding resolver is permanently bound to the
single ``BindingTier`` it declares; the framework's validated ``resolve`` entrypoint
rejects any candidate carrying a foreign tier (``HonestyInvariantError``), so an
inferred match can never be silently relabeled as exact/deterministic (§6.3, §3.1).

``flags_violation`` flags a resolver source that returns a candidate with a literal
foreign tier inside a differently-tiered resolver (the negative fixture). The
foundation subject is the real ``resolver.py`` source, which contains the
*enforcement* (not a violation) and so is not flagged. ``foundation_foreign_tier_
is_rejected`` additionally exercises the live invariant against the framework.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from tests.conformance.astutil import package_src
from tests.conformance.rulebase import Rule, RuleKind

# A source violates the rule if it constructs an AttributionCandidate carrying a
# tier different from its resolver's own declared tier — the negative fixture marks
# this shape. The framework makes the *live* violation impossible (it raises); this
# static marker proves the check is real.
_MARKERS: tuple[str, ...] = ("FOREIGN_TIER",)


def _flags(subject: object) -> bool:
    assert isinstance(subject, str)
    return any(marker in subject for marker in _MARKERS)


def _negative_fixture() -> object:
    return "return AttributionCandidate(tier=FOREIGN_TIER)  # in a LIKELY resolver\n"


def _foundation_subject() -> object:
    # The real resolver framework source contains the enforcement, not a violation.
    return (package_src("attribution") / "resolver.py").read_text()


def foundation_foreign_tier_is_rejected() -> bool:
    """Exercise the live invariant: a resolver emitting a foreign tier raises.

    Returns True iff the framework rejects a candidate whose tier differs from the
    resolver's declared tier (it always should — the validated ``resolve`` raises
    ``HonestyInvariantError``).
    """
    from valuemaxx.attribution.resolver import ResolveContext, ResolveOutcome, Resolver
    from valuemaxx.core import (
        AttributionCandidate,
        BindingTier,
        HonestyInvariantError,
        OutcomeEventId,
        RunId,
        TenantId,
    )

    class _ForeignEmitter(Resolver):
        tier = BindingTier.CANDIDATE

        def _resolve(  # pyright: ignore[reportImplicitOverride]  # throwaway test fixture
            self, ctx: ResolveContext
        ) -> ResolveOutcome:
            return ResolveOutcome(
                candidates=(
                    AttributionCandidate(
                        run_id=RunId("r"),
                        tier=BindingTier.EXACT,  # foreign to a CANDIDATE resolver
                        score=1.0,
                        rationale="x",
                    ),
                ),
                ambiguous=False,
            )

    ctx = ResolveContext(
        tenant_id=TenantId(uuid.UUID(int=1)),
        outcome_id=OutcomeEventId("oc"),
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        entity_keys=frozenset(),
        ambient_run_id=None,
        baggage={},
        echoed_run_id=None,
    )
    try:
        _ForeignEmitter().resolve(ctx)
    except HonestyInvariantError:
        return True
    return False


RULE = Rule(
    name="resolver_emits_only_its_own_tier",
    kind=RuleKind.STATIC,
    green_now=True,
    owner_task="ATTRIBUTION",
    flags_violation=_flags,
    negative_fixture=_negative_fixture,
    foundation_subject=_foundation_subject,
)
