"""DISCOVER — cluster captured calls into agents/prompts (deterministic backbone first).

§8.1's discovery is a deterministic group-by backbone that handles 70-90% for free:
calls are clustered by the highest-precedence *identity* available — a prompt-registry
``template_id``, then a ``call_site`` name, then an order-independent tool-set
fingerprint. Only the residue (no identity at all) falls to Drain skeleton
clustering; an injected :class:`~valuemaxx.core.Embedder` further sub-clusters that
residue *only when present* — when it is ``None`` the residue stays in its Drain
bucket and is **never dropped**.

Every cluster is auto-shipped ``confirmed=False``: discovery only proposes the
boundary, skeleton, task-type, and a confidence; confirming names/merges is the
onboarding agent's job, out of scope here.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from valuemaxx.eval.drain import skeleton_hash
from valuemaxx.eval.types import CapturedCall, ClusterCandidate, TaskType

if TYPE_CHECKING:
    from collections.abc import Sequence

    from valuemaxx.core import Embedder

# Structural task-type cues, checked in precedence order. The first family that
# matches a cue word wins; an unmatched prompt is conservatively OPEN_ENDED (the
# non-reconstructible bucket), never silently treated as reconstructible.
_TASK_CUES: tuple[tuple[TaskType, tuple[str, ...]], ...] = (
    (TaskType.CLASSIFICATION, ("classify", "categorize", "categorise", "label as", "is this")),
    (TaskType.EXTRACTION, ("extract", "parse", "pull the", "find the field")),
    (TaskType.DETERMINISTIC_RESOLUTION, ("resolve", "look up", "compute", "calculate")),
    (TaskType.SUMMARIZATION, ("summarize", "summarise", "tl;dr", "condense")),
)


def tool_set_fingerprint(tool_names: Sequence[str]) -> str:
    """Return an order-independent sha256 fingerprint of a tool set (§8.1).

    The fingerprint hashes the *sorted, de-duplicated* tool names, so two calls
    using the same tools in any order — or with repeats — fingerprint identically.
    """
    canonical = ",".join(sorted(set(tool_names)))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def detect_task_type(prompt: str) -> TaskType:
    """Structurally detect the task type from the prompt's cue words (§8.1).

    Structural-first: a cue word maps to a task family; an unrecognized prompt
    defaults to :attr:`~valuemaxx.eval.types.TaskType.OPEN_ENDED`, the conservative
    non-reconstructible bucket (so the honesty cap is never accidentally lifted).
    """
    lowered = prompt.lower()
    for task_type, cues in _TASK_CUES:
        if any(cue in lowered for cue in cues):
            return task_type
    return TaskType.OPEN_ENDED


def discover_clusters(
    calls: Sequence[CapturedCall], *, embedder: Embedder | None
) -> tuple[ClusterCandidate, ...]:
    """Cluster ``calls`` into agent/prompt clusters; every cluster is unconfirmed.

    Precedence: ``template_id`` > ``call_site`` > tool-set fingerprint (the
    deterministic backbone), then Drain skeleton for the no-identity residue. When
    ``embedder`` is ``None`` the residue stays in its Drain bucket — never dropped;
    when present it sub-clusters the residue. The result is deterministic and total:
    every input call lands in exactly one cluster.

    Args:
        calls: the captured calls to cluster.
        embedder: an optional injected embedder for unstructured-residue sub-clustering.

    Returns:
        The discovered clusters, sorted by cluster id for determinism.
    """
    if not calls:
        return ()

    buckets: dict[str, list[CapturedCall]] = {}
    for call in calls:
        key = _identity_key(call, embedder=embedder)
        buckets.setdefault(key, []).append(call)

    clusters: list[ClusterCandidate] = []
    for key, members in sorted(buckets.items()):
        ordered = sorted(members, key=lambda c: c.id)
        clusters.append(
            ClusterCandidate(
                cluster_id=key,
                member_ids=tuple(c.id for c in ordered),
                skeleton_hash=skeleton_hash(ordered[0].prompt),
                task_type=_cluster_task_type(ordered),
                confidence=_confidence(key, ordered),
            )
        )
    return tuple(clusters)


def _identity_key(call: CapturedCall, *, embedder: Embedder | None) -> str:
    """The clustering key for one call, by identity precedence then Drain residue."""
    if call.template_id is not None:
        return f"tmpl:{call.template_id}"
    if call.call_site:
        return f"site:{call.call_site}"
    if call.tool_names:
        return f"tools:{tool_set_fingerprint(call.tool_names)}"
    skeleton = skeleton_hash(call.prompt)
    if embedder is None:
        # No embedder: residue stays in its Drain skeleton bucket (never dropped).
        return f"drain:{skeleton}"
    # An embedder sub-clusters the residue; the deterministic stub keys the bucket
    # by the rounded embedding so the assignment is reproducible under test.
    vector = embedder.embed([call.prompt])[0]
    embed_key = ",".join(f"{v:.4f}" for v in vector)
    return f"embed:{hashlib.sha256(embed_key.encode('utf-8')).hexdigest()}"


def _cluster_task_type(members: Sequence[CapturedCall]) -> TaskType:
    """The cluster's task type: the structurally-detected type of its first member.

    Members of one identity cluster share a call-site/template/tool-set, so their
    structural task type is homogeneous; the first member is representative.
    """
    return detect_task_type(members[0].prompt)


def _confidence(key: str, members: Sequence[CapturedCall]) -> float:
    """A discovery confidence in [0, 1]: identity-keyed clusters are high-confidence.

    Template/call-site/tool identity is a strong deterministic signal (0.95); Drain
    and embedding residue are softer (0.7), reflecting §8.1's "deterministic backbone
    first, fuzzy residue last".
    """
    return 0.95 if key.startswith(("tmpl:", "site:", "tools:")) else 0.7


__all__ = ["detect_task_type", "discover_clusters", "tool_set_fingerprint"]
