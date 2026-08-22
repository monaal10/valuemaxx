"""Structural traffic lints that make no claim about prompt semantics."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

from valuemaxx.core.optimization import EvidenceTier, LinterFinding, LinterFindingKind

if TYPE_CHECKING:
    from collections.abc import Sequence

    from valuemaxx.core import TenantId


@dataclass(frozen=True, slots=True)
class PromptBlock:
    """One already-parsed message/tool block in request order."""

    role: str
    content: str


@dataclass(frozen=True, slots=True)
class TrafficCall:
    """The structural fields required by the linter for one captured call."""

    call_id: str
    run_id: str
    request_body: str
    blocks: tuple[PromptBlock, ...]


def lint_traffic(
    *, tenant_id: TenantId, call_site_id: str, calls: Sequence[TrafficCall]
) -> tuple[LinterFinding, ...]:
    """Return cache-layout and exact-within-run duplicate facts."""
    findings: list[LinterFinding] = []
    cache = _cache_misalignment(tenant_id=tenant_id, call_site_id=call_site_id, calls=calls)
    if cache is not None:
        findings.append(cache)
    findings.extend(_duplicates(tenant_id=tenant_id, call_site_id=call_site_id, calls=calls))
    return tuple(findings)


def _cache_misalignment(
    *, tenant_id: TenantId, call_site_id: str, calls: Sequence[TrafficCall]
) -> LinterFinding | None:
    if len(calls) < 2:
        return None
    common_length = min(len(call.blocks) for call in calls)
    stable = [
        len({(call.blocks[index].role, call.blocks[index].content) for call in calls}) == 1
        for index in range(common_length)
    ]
    volatile_indexes = [index for index, is_stable in enumerate(stable) if not is_stable]
    if not volatile_indexes:
        return None
    first_volatile = volatile_indexes[0]
    suffix_indexes = [index for index in range(first_volatile + 1, common_length) if stable[index]]
    if not suffix_indexes:
        return None
    stable_chars = sum(len(calls[0].blocks[index].content) for index in suffix_indexes)
    evidence = (
        f"{stable_chars} stable characters in {len(suffix_indexes)} block(s) occur after "
        f"volatile block {first_volatile} across {len(calls)} calls"
    )
    return _finding(
        tenant_id=tenant_id,
        call_site_id=call_site_id,
        kind=LinterFindingKind.CACHE_MISALIGNMENT,
        summary="Stable prompt content follows volatile content",
        evidence=evidence,
    )


def _duplicates(
    *, tenant_id: TenantId, call_site_id: str, calls: Sequence[TrafficCall]
) -> tuple[LinterFinding, ...]:
    groups: dict[tuple[str, str], list[str]] = {}
    for call in calls:
        groups.setdefault((call.run_id, call.request_body), []).append(call.call_id)
    findings: list[LinterFinding] = []
    for (run_id, request_body), call_ids in sorted(groups.items()):
        if len(call_ids) < 2:
            continue
        body_hash = hashlib.sha256(request_body.encode("utf-8")).hexdigest()
        findings.append(
            _finding(
                tenant_id=tenant_id,
                call_site_id=call_site_id,
                kind=LinterFindingKind.DUPLICATE_CALL,
                summary="Exact request body repeated within one run",
                evidence=(
                    f"run {run_id} sent byte-identical body {body_hash} in calls "
                    f"{', '.join(sorted(call_ids))}"
                ),
            )
        )
    return tuple(findings)


def _finding(
    *,
    tenant_id: TenantId,
    call_site_id: str,
    kind: LinterFindingKind,
    summary: str,
    evidence: str,
) -> LinterFinding:
    identifier = hashlib.sha256(f"{call_site_id}:{kind.value}:{evidence}".encode()).hexdigest()
    return LinterFinding(
        tenant_id=tenant_id,
        id=f"finding-{identifier}",
        call_site_id=call_site_id,
        kind=kind,
        summary=summary,
        evidence=evidence,
        evidence_tier=EvidenceTier.STATIC,
    )


__all__ = ["PromptBlock", "TrafficCall", "lint_traffic"]
