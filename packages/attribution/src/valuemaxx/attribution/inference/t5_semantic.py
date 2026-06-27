"""T5 semantic-inference resolver — ``likely``; the labeled last resort (§6.3).

For outcomes that happen entirely in an external UI with no shared id, an injected
:class:`~valuemaxx.core.LlmJudge` reasons over entity + time + content to propose a
binding. This is the lowest-trust cascade tier: it produces only the ``likely``
tier, the cascade ALWAYS review-queues it, and it is NEVER fed to billing-grade
metrics (§4).

The judge is **injected** so tests are deterministic — there is never a hard
dependency on a real model. When no judge is configured the resolver is DISABLED
(``matched=False``); it never silently falls back to a real model.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from typing_extensions import override
from valuemaxx.attribution.resolver import ResolveContext, ResolveOutcome, Resolver, no_match
from valuemaxx.core import BindingTier

if TYPE_CHECKING:
    from datetime import timedelta

    from valuemaxx.core import AttributionCandidate, LlmJudge, Run, RunRepository

_DEFAULT_THRESHOLD = 0.5

_RUBRIC = (
    "Given the outcome's content and a candidate agent run (its agent, time, and "
    "entity keys), score 0..1 how likely this run produced this outcome. This is an "
    "advisory, review-queued inference and must never be treated as billing-grade."
)


class SemanticInferenceResolver(Resolver):
    """T5: LLM-judge inference over entity + time + content (likely tier)."""

    tier = BindingTier.LIKELY

    def __init__(
        self,
        *,
        run_repo: RunRepository,
        judge: LlmJudge | None,
        window: timedelta,
        threshold: float = _DEFAULT_THRESHOLD,
    ) -> None:
        """Configure the resolver.

        Args:
            run_repo: the tenant-scoped run repository to draw candidate runs from.
            judge: the injected LLM-judge; ``None`` disables this tier entirely.
            window: the symmetric ``±window`` around the outcome time within which
                a run is eligible to be judged.
            threshold: the minimum judge score (0..1) for a run to be emitted as a
                likely candidate.
        """
        self._run_repo = run_repo
        self._judge = judge
        self._window = window
        self._threshold = threshold

    @override
    def _resolve(self, ctx: ResolveContext) -> ResolveOutcome:
        # Disabled when no judge is injected — never falls back to a real model.
        if self._judge is None:
            return no_match()

        candidates: list[AttributionCandidate] = []
        for run in self._candidate_runs(ctx):
            score = self._judge.grade(
                prediction=ctx.content,
                reference=self._run_summary(run),
                rubric=_RUBRIC,
            )
            if score >= self._threshold:
                candidates.append(
                    self.candidate(
                        run_id=run.id,
                        score=score,
                        rationale=f"semantic inference (judge score {score:.2f})",
                    )
                )
        if not candidates:
            return no_match()
        return self.matched_outcome(candidates)

    def _candidate_runs(self, ctx: ResolveContext) -> list[Run]:
        """In-window, de-duplicated runs sharing any of the outcome's entity keys."""
        seen: dict[str, Run] = {}
        window_seconds = self._window.total_seconds()
        for entity_key in ctx.entity_keys:
            for run in self._run_repo.list_by_entity(ctx.tenant_id, entity_key):
                distance = abs((run.started_at - ctx.occurred_at).total_seconds())
                if distance <= window_seconds and run.id not in seen:
                    seen[run.id] = run
        return list(seen.values())

    @staticmethod
    def _run_summary(run: Run) -> str:
        """A compact textual summary of a run for the judge to reason over."""
        agent = run.agent_name or "unknown-agent"
        keys = ", ".join(f"{k}={v}" for k, v in sorted(run.entity_keys))
        return f"run {run.id} (agent={agent}, started_at={run.started_at.isoformat()}, {keys})"


__all__ = ["SemanticInferenceResolver"]
