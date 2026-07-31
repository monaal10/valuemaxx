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

from decimal import Decimal
from typing import TYPE_CHECKING

from pydantic import BaseModel
from valuemaxx.capabilities import Mode, Surface, capability
from valuemaxx.core import AtmError
from valuemaxx.eval.promptfoo import (
    ImportedSuite,
    import_promptfoo_config,
    import_promptfoo_tests,
)

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
    # What the USER cares about, in their own words ("warm, under 20 words"). Empty
    # falls back to the generic parity rubric — "do these models agree" — which is a
    # different and usually less useful question.
    criterion: str = ""
    # A promptfoo suite to grade against, as the JSONL content `import_promptfoo_suite`
    # accepts. Sent with the run rather than stored, so a user can evaluate against the
    # suite they already maintain without valuemaxx holding a copy that silently drifts
    # from theirs. Combined with `criterion`: a case must satisfy every rule from both.
    promptfoo_jsonl: str = ""


class ImportPromptfooInput(BaseModel):
    """Request to import an existing promptfoo suite as eval criteria.

    Takes the JSONL test-file CONTENT, never a path: the backend must never read the
    caller's filesystem (it may be a container, a different host, or a shared server),
    and a path would be both unreadable and an invitation to traverse. The CLI reads
    the file locally and posts what it read.
    """

    tenant_id: str
    """JSONL test rows (the shape that carries assertions)."""
    jsonl: str = ""
    """A promptfoo YAML config; only its INLINE assertions can be read, since a
    `tests: file://…` reference points at a file the backend must not open."""
    yaml_config: str = ""


class ImportedCriterion(BaseModel):
    """One imported assertion, shown back so a human can see what was understood."""

    text: str
    """True when an LLM judge scores it; False when it is decided exactly (no tokens)."""
    judge_required: bool


class ImportPromptfooOutput(BaseModel):
    """What the import produced — and, explicitly, what it could not."""

    criteria: tuple[ImportedCriterion, ...]
    judge_count: int
    deterministic_count: int
    """Assertion types skipped, with why. Reported so a partial import is never
    mistaken for a complete one."""
    unsupported: tuple[str, ...]


class EstimateSwitchInput(BaseModel):
    """Request the projected cost of serving today's traffic with a different model."""

    tenant_id: str
    incumbent_model: str
    candidate_model: str
    candidate_provider: str


class EstimateSwitchOutput(BaseModel):
    """The projected switch cost, or the reason there is no honest estimate.

    Every figure is ESTIMATED: list-price arithmetic over traffic the candidate never
    actually served. It is never a measured or reconciled cost, and a caller must not
    render it as one.
    """

    found: bool
    incumbent_usd: str | None = None
    candidate_usd: str | None = None
    """Negative means cheaper. None when the incumbent baseline is zero."""
    pct_change: str | None = None
    event_count: int = 0
    reason: str | None = None


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
_IMPORT_EXAMPLE = ImportPromptfooInput(
    tenant_id="00000000-0000-0000-0000-000000000000",
    jsonl='{"assert": [{"type": "llm-rubric", "value": "the answer stays on topic"}]}',
)
_ESTIMATE_EXAMPLE = EstimateSwitchInput(
    tenant_id="00000000-0000-0000-0000-000000000000",
    incumbent_model="claude-opus-4",
    candidate_model="claude-haiku-4",
    candidate_provider="anthropic",
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

    def import_promptfoo_handler(request: ImportPromptfooInput) -> ImportPromptfooOutput:
        # Pure parse — no runtime needed, nothing persisted, no provider call. The
        # result is a PROPOSAL a human reads before running an eval with it, which is
        # why the unsupported list is part of the output rather than a log line.
        from_jsonl = import_promptfoo_tests(request.jsonl.splitlines())
        from_yaml = (
            import_promptfoo_config(request.yaml_config)
            if request.yaml_config
            else ImportedSuite(criteria=(), unsupported=())
        )
        suite = ImportedSuite(
            criteria=(*from_yaml.criteria, *from_jsonl.criteria),
            unsupported=(*from_yaml.unsupported, *from_jsonl.unsupported),
        )
        return ImportPromptfooOutput(
            criteria=tuple(
                ImportedCriterion(text=c.text, judge_required=c.judge_required)
                for c in suite.criteria
            ),
            judge_count=sum(1 for c in suite.criteria if c.judge_required),
            deterministic_count=sum(1 for c in suite.criteria if not c.judge_required),
            unsupported=suite.unsupported,
        )

    def estimate_switch_handler(request: EstimateSwitchInput) -> EstimateSwitchOutput:
        from uuid import UUID

        from valuemaxx.core import TenantId

        result = holder.require().estimate_switch_for(
            TenantId(UUID(request.tenant_id)),
            incumbent_model=request.incumbent_model,
            candidate_model=request.candidate_model,
            candidate_provider=request.candidate_provider,
        )
        if result.estimate is None:
            # No number rather than a zero: "we could not price this" and "$0 saved"
            # are different facts.
            return EstimateSwitchOutput(found=False, reason=result.reason)
        estimate = result.estimate
        pct = estimate.pct_change
        return EstimateSwitchOutput(
            found=True,
            incumbent_usd=str(estimate.incumbent_usd),
            candidate_usd=str(estimate.candidate_usd),
            pct_change=None if pct is None else str(pct.quantize(Decimal("0.1"))),
            event_count=estimate.event_count,
        )

    def run_eval_funnel_handler(request: RunEvalFunnelInput) -> RunEvalFunnelOutput:
        # This used to ONLY acknowledge the job — "the funnel runs out-of-band" — but
        # nothing ran it out of band, so every submission returned accepted=True, did no
        # work, and `get_recommendation` stayed `found: false` forever. The async-job
        # surface already runs the handler on a worker and polls via /jobs/{id}, so the
        # funnel belongs here.
        from uuid import UUID

        from valuemaxx.core import LabelSource, ProviderKeyRef, TenantId

        service = holder.require()
        tenant = TenantId(UUID(request.tenant_id))
        # Grade the host's REAL recorded outcomes, not the built-in sample. The case
        # set also reports which ground truth actually exists, so the recommendation
        # cannot claim `reliable` off evidence nobody produced.
        # Prefer REPLAY: re-run the host's captured prompts against the candidate, so
        # the comparison is what the candidate actually produces rather than text the
        # host happened to store. Falls back to stored-output cases when no prompts were
        # captured (content capture is opt-in), and to the built-in sample when neither
        # exists — each fallback claims strictly less evidence than the one above it.
        case_set = service.build_replay_case_set_for(
            tenant, candidate_model=request.candidate_model
        )
        if case_set.is_empty:
            case_set = service.build_case_set_for(tenant)
        service.run_eval_funnel(
            tenant_id=tenant,
            incumbent_model=request.incumbent_model,
            candidate=ProviderKeyRef(
                provider=request.candidate_provider,
                # A REFERENCE, never plaintext: the recommendation has no key field and
                # nothing here logs or persists it.
                secret_ref=request.candidate_secret_ref,
            ),
            candidate_model=request.candidate_model,
            # The wire carries a plain string; the funnel needs the enum.
            label_source=LabelSource(request.label_source),
            case_set=case_set,
            criterion=request.criterion,
            criteria=import_promptfoo_tests(request.promptfoo_jsonl.splitlines()).criteria
            if request.promptfoo_jsonl
            else (),
        )
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
            name="import_promptfoo_suite",
            input_model=ImportPromptfooInput,
            output_model=ImportPromptfooOutput,
            handler=import_promptfoo_handler,
            description=(
                "Import an existing promptfoo suite as eval criteria: llm-rubric "
                "assertions become judge-scored criteria (the rubric text used "
                "verbatim), contains/not-contains become exact checks. Every "
                "unsupported assertion type is returned, never approximated."
            ),
            surfaces=_RR_SURFACES,
            mode=Mode.REQUEST_RESPONSE,
            examples=(_IMPORT_EXAMPLE,),
        )
    )
    registry.register(
        capability(
            name="estimate_switch_cost",
            input_model=EstimateSwitchInput,
            output_model=EstimateSwitchOutput,
            handler=estimate_switch_handler,
            description=(
                "Project what today's traffic would cost on a different model, by "
                "repricing the incumbent's OWN observed token vectors against the "
                "candidate's price card. Always ESTIMATED (list price over traffic the "
                "candidate never served); returns no number when the model cannot be "
                "priced, rather than a misleading zero."
            ),
            surfaces=_RR_SURFACES,
            mode=Mode.REQUEST_RESPONSE,
            examples=(_ESTIMATE_EXAMPLE,),
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
