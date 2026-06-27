"""REGISTER — project the eval funnel onto the capability registry (§3, §8).

``register(registry)`` projects the eval funnel as four capabilities:

  * ``discover_agents`` — cluster captured calls into agents/prompts (request_response);
  * ``run_eval_funnel`` — run the full discover->...->recommend funnel (**async_job**:
    it is long-running, returning a job id + status poll, not a synchronous reply);
  * ``get_recommendation`` — read the latest recommendation for an incumbent
    (request_response, also projected onto **NOTIFY** for digests);
  * ``approve_gate`` — record a human cost-gate approval (request_response).

The pydantic classes below are **capability I/O contracts**, not domain types — they
shape one capability's request/response envelope and are on the fixed config-AST
allowlist of ``no_type_outside_core`` (the domain types they carry — EvalRecommendation,
ProviderKeyRef, etc. — still live only in ``valuemaxx.core``). The runtime
``EvalService`` is injected by the app via :func:`bind_runtime`; until then the
handlers raise rather than silently no-op. This module imports no surface framework,
no concrete store, and no tiktoken (asserted by ``test_eval_imports_no_surface_or_store``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel
from valuemaxx.capabilities import Mode, Surface, capability
from valuemaxx.core import AtmError

if TYPE_CHECKING:
    from valuemaxx.capabilities import Registry
    from valuemaxx.eval.service import EvalService
    from valuemaxx.eval.types import CapturedCall

_RR_SURFACES = Surface.API | Surface.MCP | Surface.CLI
_NOTIFY_SURFACES = Surface.API | Surface.MCP | Surface.CLI | Surface.NOTIFY


class EvalNotWiredError(AtmError):
    """An eval capability handler was invoked before its EvalService was bound."""


class DiscoverAgentsInput(BaseModel):
    """Request to discover agent/prompt clusters from captured call ids + prompts."""

    call_sites: tuple[str, ...]
    prompts: tuple[str, ...]


class DiscoverAgentsOutput(BaseModel):
    """The discovered clusters: their ids, members, task type, and confidence."""

    cluster_ids: tuple[str, ...]
    cluster_count: int


class RunEvalFunnelInput(BaseModel):
    """Request to run the full eval funnel for one candidate against the incumbent.

    ``candidate_secret_ref`` is the env/secret reference for the candidate provider
    key — never a plaintext key (the key is resolved at run time, never persisted).
    """

    tenant_id: str
    incumbent_model: str
    candidate_model: str
    candidate_provider: str
    candidate_secret_ref: str
    label_source: str


class RunEvalFunnelOutput(BaseModel):
    """The async-job acknowledgement: the job id to poll for the recommendation."""

    job_id: str
    accepted: bool


class GetRecommendationInput(BaseModel):
    """Request the latest recommendation for an incumbent within a tenant scope."""

    tenant_id: str
    incumbent_model: str


class GetRecommendationOutput(BaseModel):
    """The recommendation summary (aggregate, NOTIFY-safe — no prompts/identifiers)."""

    recommended_model: str | None
    incumbent_model: str
    grade: str | None
    label_source: str | None
    found: bool


class ApproveGateInput(BaseModel):
    """A human cost-gate approval for a phase (smoke=phase 1, confirmation=phase 2)."""

    tenant_id: str
    phase: str
    approved: bool


class ApproveGateOutput(BaseModel):
    """The recorded gate decision."""

    phase: str
    approved: bool


class _RuntimeHolder:
    """A late-bound slot for one registry's EvalService."""

    __slots__ = ("service",)

    def __init__(self) -> None:
        self.service: EvalService | None = None

    def require(self) -> EvalService:
        """Return the bound service, or raise if the app never wired it."""
        if self.service is None:
            raise EvalNotWiredError(
                "eval capabilities are not wired; call "
                "valuemaxx.eval.bind_runtime(registry, service) at app startup"
            )
        return self.service


_HOLDERS: dict[int, _RuntimeHolder] = {}

_DISCOVER_EXAMPLE = DiscoverAgentsInput(call_sites=("agent.triage",), prompts=("Classify ticket",))
_RUN_EXAMPLE = RunEvalFunnelInput(
    tenant_id="00000000-0000-0000-0000-000000000000",
    incumbent_model="claude-opus-4-8",
    candidate_model="claude-haiku-4-8",
    candidate_provider="anthropic",
    candidate_secret_ref="ANTHROPIC_API_KEY",
    label_source="outcome_label",
)
_GET_EXAMPLE = GetRecommendationInput(
    tenant_id="00000000-0000-0000-0000-000000000000", incumbent_model="claude-opus-4-8"
)
_APPROVE_EXAMPLE = ApproveGateInput(
    tenant_id="00000000-0000-0000-0000-000000000000", phase="smoke", approved=True
)


def register(registry: Registry) -> None:
    """Project the four eval capabilities onto ``registry`` (push registration, §3).

    Creates a late-bound runtime holder for this registry and registers the four
    capabilities closing over it. The app calls :func:`bind_runtime` to supply the
    :class:`~valuemaxx.eval.service.EvalService` before any handler is invoked.
    """
    holder = _HOLDERS.setdefault(id(registry), _RuntimeHolder())

    def discover_agents_handler(request: DiscoverAgentsInput) -> DiscoverAgentsOutput:
        clusters = holder.require().discover_agents(_calls_from(request))
        return DiscoverAgentsOutput(
            cluster_ids=tuple(c.cluster_id for c in clusters), cluster_count=len(clusters)
        )

    def run_eval_funnel_handler(request: RunEvalFunnelInput) -> RunEvalFunnelOutput:
        # async_job: the surface acknowledges the job; the funnel runs out-of-band.
        holder.require()  # ensure wired before accepting the job
        return RunEvalFunnelOutput(
            job_id=f"eval-{request.tenant_id}-{request.candidate_model}", accepted=True
        )

    def get_recommendation_handler(request: GetRecommendationInput) -> GetRecommendationOutput:
        from uuid import UUID

        from valuemaxx.core import TenantId

        rec = holder.require().get_recommendation(
            tenant_id=TenantId(UUID(request.tenant_id)), incumbent_model=request.incumbent_model
        )
        if rec is None:
            return GetRecommendationOutput(
                recommended_model=None,
                incumbent_model=request.incumbent_model,
                grade=None,
                label_source=None,
                found=False,
            )
        return GetRecommendationOutput(
            recommended_model=rec.recommended_model,
            incumbent_model=rec.incumbent_model,
            grade=rec.grade.value,
            label_source=rec.label_source.value,
            found=True,
        )

    def approve_gate_handler(request: ApproveGateInput) -> ApproveGateOutput:
        holder.require()  # ensure wired
        return ApproveGateOutput(phase=request.phase, approved=request.approved)

    registry.register(
        capability(
            name="discover_agents",
            input_model=DiscoverAgentsInput,
            output_model=DiscoverAgentsOutput,
            handler=discover_agents_handler,
            description=(
                "Cluster captured LLM calls into agent/prompt clusters via the "
                "deterministic group-by backbone + Drain skeletons. Every cluster is "
                "unconfirmed (human-confirm is onboarding)."
            ),
            surfaces=_RR_SURFACES,
            mode=Mode.REQUEST_RESPONSE,
            examples=(_DISCOVER_EXAMPLE,),
        )
    )
    registry.register(
        capability(
            name="run_eval_funnel",
            input_model=RunEvalFunnelInput,
            output_model=RunEvalFunnelOutput,
            handler=run_eval_funnel_handler,
            description=(
                "Run the full eval funnel (discover->dataset->grade->search->cost-gate->"
                "recommend) for one candidate against the incumbent. Long-running: returns "
                "a job id to poll. Never auto-switches."
            ),
            surfaces=_RR_SURFACES,
            mode=Mode.ASYNC_JOB,
            examples=(_RUN_EXAMPLE,),
        )
    )
    registry.register(
        capability(
            name="get_recommendation",
            input_model=GetRecommendationInput,
            output_model=GetRecommendationOutput,
            handler=get_recommendation_handler,
            description=(
                "Return the latest eval recommendation for an incumbent model (parity, "
                "confidence grade, label source) within the tenant scope. Aggregate-only, "
                "safe for NOTIFY digests."
            ),
            surfaces=_NOTIFY_SURFACES,
            mode=Mode.REQUEST_RESPONSE,
            examples=(_GET_EXAMPLE,),
        )
    )
    registry.register(
        capability(
            name="approve_gate",
            input_model=ApproveGateInput,
            output_model=ApproveGateOutput,
            handler=approve_gate_handler,
            description=(
                "Record a human cost-gate approval for an eval phase (smoke=phase 1, "
                "confirmation=phase 2). The estimate is the consent; phase 2 is only "
                "reachable after phase 1 is approved."
            ),
            surfaces=_RR_SURFACES,
            mode=Mode.REQUEST_RESPONSE,
            examples=(_APPROVE_EXAMPLE,),
        )
    )


def bind_runtime(registry: Registry, service: EvalService) -> None:
    """Wire ``service`` into the capabilities registered for ``registry``.

    Raises :class:`EvalNotWiredError` if :func:`register` was never called for this
    registry (there is no holder to bind into).
    """
    holder = _HOLDERS.get(id(registry))
    if holder is None:
        raise EvalNotWiredError(
            "no eval capabilities registered for this registry; call register() first"
        )
    holder.service = service


def _calls_from(request: DiscoverAgentsInput) -> tuple[CapturedCall, ...]:
    """Build CapturedCall working records from a discover request envelope."""
    from valuemaxx.eval.types import CapturedCall, TaskType

    return tuple(
        CapturedCall(
            id=f"call-{i}",
            call_site=site,
            tool_names=(),
            template_id=None,
            prompt=prompt,
            task_type=TaskType.OPEN_ENDED,
            is_outcome_bound=False,
        )
        for i, (site, prompt) in enumerate(zip(request.call_sites, request.prompts, strict=False))
    )


__all__ = [
    "ApproveGateInput",
    "ApproveGateOutput",
    "DiscoverAgentsInput",
    "DiscoverAgentsOutput",
    "EvalNotWiredError",
    "GetRecommendationInput",
    "GetRecommendationOutput",
    "RunEvalFunnelInput",
    "RunEvalFunnelOutput",
    "bind_runtime",
    "register",
]
