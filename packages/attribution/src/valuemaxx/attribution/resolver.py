"""The resolver framework + the resolver-emits-only-its-own-tier invariant (ATTR-0).

A :class:`Resolver` is one tier of the binding cascade (§6.3). Each resolver is
permanently bound to the single :class:`~valuemaxx.core.BindingTier` it may ever
produce (its class-level ``tier``). Subclasses implement :meth:`Resolver._resolve`;
the framework's :meth:`Resolver.resolve` template method validates every emitted
candidate carries the resolver's own tier — a candidate with a foreign tier raises
:class:`~valuemaxx.core.HonestyInvariantError`, so an inferred match can never be
silently mis-labeled as exact (the ``resolver_emits_only_its_own_tier`` rule).

``ResolveContext`` / ``ResolveOutcome`` are plain dataclasses (cascade control
structures, not domain models — domain types live only in ``valuemaxx.core``).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, final

from valuemaxx.core import (
    AttributionCandidate,
    BindingTier,
    HonestyInvariantError,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from datetime import datetime

    from valuemaxx.core import OutcomeEventId, RunId, TenantId


@dataclass(frozen=True, slots=True)
class ResolveContext:
    """Everything a resolver may read to bind one outcome to a run.

    Carries the per-tier signals (ambient run id, W3C baggage map, the echoed
    round-trip run id) alongside the outcome's tenant scope, identity, time,
    entity keys, and textual content. Each resolver reads only the signals
    relevant to its own tier.
    """

    tenant_id: TenantId
    outcome_id: OutcomeEventId
    occurred_at: datetime
    entity_keys: frozenset[tuple[str, str]]
    ambient_run_id: RunId | None
    baggage: Mapping[str, str]
    echoed_run_id: RunId | None
    content: str = ""


@dataclass(frozen=True, slots=True)
class ResolveOutcome:
    """The result of one resolver: its candidates plus an ``ambiguous`` flag.

    ``matched`` is derived (any candidates present). ``ambiguous`` is set by a
    resolver that found multiple equally-plausible runs it cannot disambiguate
    (the cascade halts such an outcome to human review rather than guessing).
    """

    candidates: tuple[AttributionCandidate, ...] = ()
    ambiguous: bool = False

    @property
    def matched(self) -> bool:
        """True iff the resolver produced at least one candidate."""
        return len(self.candidates) > 0


def no_match() -> ResolveOutcome:
    """An empty, unambiguous outcome — the resolver bound nothing."""
    return ResolveOutcome(candidates=(), ambiguous=False)


class Resolver(ABC):
    """One tier of the binding cascade, bound to a single emittable tier.

    Subclasses declare a class-level ``tier`` and implement :meth:`_resolve`. The
    framework :meth:`resolve` validates that every emitted candidate carries that
    tier; a foreign tier is an honesty-axis violation and raises.
    """

    tier: ClassVar[BindingTier]

    def __init_subclass__(cls, **kwargs: object) -> None:
        """Require every concrete resolver to declare exactly one ``tier``.

        Abstract intermediate bases (those still carrying ``__abstractmethods__``)
        may omit ``tier``; a concrete resolver that never declares one — directly
        or inherited from a concrete parent — is a hard error.
        """
        super().__init_subclass__(**kwargs)
        abstract_methods: frozenset[str] = getattr(cls, "__abstractmethods__", frozenset())
        is_concrete = not abstract_methods
        if is_concrete and not isinstance(getattr(cls, "tier", None), BindingTier):
            raise TypeError(
                f"resolver {cls.__name__!r} must declare a class-level BindingTier ``tier``"
            )

    @abstractmethod
    def _resolve(self, ctx: ResolveContext) -> ResolveOutcome:
        """Produce candidates for ``ctx`` (each must carry ``self.tier``)."""

    @final
    def resolve(self, ctx: ResolveContext) -> ResolveOutcome:
        """Resolve ``ctx`` and validate every candidate carries this resolver's tier.

        Raises :class:`~valuemaxx.core.HonestyInvariantError` if a candidate carries
        any tier other than ``self.tier`` — a labeled match is never mis-tiered.
        """
        outcome = self._resolve(ctx)
        for candidate in outcome.candidates:
            if candidate.tier is not self.tier:
                raise HonestyInvariantError(
                    f"resolver {type(self).__name__!r} (tier={self.tier.value}) emitted a "
                    f"candidate with foreign tier {candidate.tier.value}"
                )
        return outcome

    def candidate(self, *, run_id: RunId, score: float, rationale: str) -> AttributionCandidate:
        """Build an :class:`~valuemaxx.core.AttributionCandidate` stamped with this tier.

        The helper always stamps ``self.tier`` so a resolver cannot accidentally
        emit a candidate of a different tier.
        """
        return AttributionCandidate(
            run_id=run_id,
            tier=self.tier,
            score=score,
            rationale=rationale,
        )

    def matched_outcome(
        self, candidates: Sequence[AttributionCandidate], *, ambiguous: bool = False
    ) -> ResolveOutcome:
        """Wrap ``candidates`` (already stamped with this tier) into a matched outcome."""
        return ResolveOutcome(candidates=tuple(candidates), ambiguous=ambiguous)


__all__ = [
    "AttributionCandidate",
    "ResolveContext",
    "ResolveOutcome",
    "Resolver",
    "no_match",
]
