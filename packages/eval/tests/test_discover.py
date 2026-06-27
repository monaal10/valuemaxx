"""DISCOVER: cluster captured calls into agents/prompts (deterministic backbone first)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from valuemaxx.eval.discover import (
    detect_task_type,
    discover_clusters,
    tool_set_fingerprint,
)
from valuemaxx.eval.types import CapturedCall, TaskType

if TYPE_CHECKING:
    from collections.abc import Sequence


class _StubEmbedder:
    """A deterministic stub embedder: a 1-d embedding keyed by the prompt's length parity."""

    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        return [[float(len(t) % 2)] for t in texts]


def _call(
    cid: str,
    *,
    call_site: str = "",
    tools: tuple[str, ...] = (),
    template_id: str | None = None,
    prompt: str = "do a thing",
    task_type: TaskType = TaskType.OPEN_ENDED,
    outcome_bound: bool = False,
) -> CapturedCall:
    return CapturedCall(
        id=cid,
        call_site=call_site,
        tool_names=tools,
        template_id=template_id,
        prompt=prompt,
        task_type=task_type,
        is_outcome_bound=outcome_bound,
    )


# ---------------------------------------------------------------- tool_set_fingerprint


def test_tool_set_fingerprint_order_independent() -> None:
    """The fingerprint hashes the SORTED tool set — order does not matter."""
    assert tool_set_fingerprint(("b", "a", "c")) == tool_set_fingerprint(("c", "a", "b"))


def test_tool_set_fingerprint_dedups() -> None:
    """Duplicate tool names do not change the fingerprint (it is a set)."""
    assert tool_set_fingerprint(("a", "a", "b")) == tool_set_fingerprint(("a", "b"))


def test_tool_set_fingerprint_distinguishes_different_sets() -> None:
    """Different tool sets fingerprint differently."""
    assert tool_set_fingerprint(("a", "b")) != tool_set_fingerprint(("a", "c"))


def test_empty_tool_set_has_stable_fingerprint() -> None:
    """The empty tool set has a stable, deterministic fingerprint."""
    assert tool_set_fingerprint(()) == tool_set_fingerprint(())


# ---------------------------------------------------------------- detect_task_type


def test_detect_task_type_classification_structural() -> None:
    """A 'classify'/'categorize' prompt is structurally detected as classification."""
    detected = detect_task_type("Classify this support ticket into a category")
    assert detected is TaskType.CLASSIFICATION


def test_detect_task_type_extraction_structural() -> None:
    """An 'extract the fields' prompt is structurally detected as extraction."""
    detected = detect_task_type("Extract the invoice number and total from this")
    assert detected is TaskType.EXTRACTION


def test_detect_task_type_summarization_structural() -> None:
    """A 'summarize' prompt is detected as summarization (open-ended family)."""
    assert detect_task_type("Summarize the following thread") is TaskType.SUMMARIZATION


def test_detect_task_type_defaults_open_ended() -> None:
    """An unrecognized prompt defaults to open-ended (the conservative bucket)."""
    assert detect_task_type("Write a friendly reply to the customer") is TaskType.OPEN_ENDED


# ---------------------------------------------------------------- discover_clusters


def test_group_by_call_site_identity() -> None:
    """Calls with the same call-site identity cluster together (the deterministic backbone)."""
    calls = [
        _call("a", call_site="agent.reply", prompt="x"),
        _call("b", call_site="agent.reply", prompt="y"),
        _call("c", call_site="agent.triage", prompt="z"),
    ]
    clusters = discover_clusters(calls, embedder=None)
    members = {frozenset(c.member_ids) for c in clusters}
    assert frozenset({"a", "b"}) in members
    assert frozenset({"c"}) in members


def test_group_by_tool_set_when_no_call_site() -> None:
    """With no call-site, calls cluster by their order-independent tool fingerprint."""
    calls = [
        _call("a", tools=("search", "lookup")),
        _call("b", tools=("lookup", "search")),  # same set, different order
        _call("c", tools=("email",)),
    ]
    clusters = discover_clusters(calls, embedder=None)
    members = {frozenset(c.member_ids) for c in clusters}
    assert frozenset({"a", "b"}) in members
    assert frozenset({"c"}) in members


def test_template_id_identity_clusters() -> None:
    """A prompt-registry template id is an identity key (highest-precedence backbone)."""
    calls = [
        _call("a", template_id="tmpl-7", prompt="alpha"),
        _call("b", template_id="tmpl-7", prompt="beta"),
    ]
    clusters = discover_clusters(calls, embedder=None)
    assert any(frozenset(c.member_ids) == frozenset({"a", "b"}) for c in clusters)


def test_drain_clusters_residue_when_no_identity() -> None:
    """With no identity signal, residue calls fall to Drain skeleton clustering."""
    calls = [
        _call("a", prompt="Refund order 111 for user 222"),
        _call("b", prompt="Refund order 999 for user 333"),  # same skeleton
        _call("c", prompt="Cancel subscription 5"),
    ]
    clusters = discover_clusters(calls, embedder=None)
    members = {frozenset(c.member_ids) for c in clusters}
    assert frozenset({"a", "b"}) in members
    assert frozenset({"c"}) in members


def test_no_run_is_ever_dropped() -> None:
    """Every captured call lands in exactly one cluster — nothing is dropped."""
    calls = [
        _call("a", call_site="x"),
        _call("b", tools=("t",)),
        _call("c", template_id="tm"),
        _call("d", prompt="totally unstructured residue"),
    ]
    clusters = discover_clusters(calls, embedder=None)
    assigned = [mid for c in clusters for mid in c.member_ids]
    assert sorted(assigned) == ["a", "b", "c", "d"]
    assert len(assigned) == len(set(assigned))  # no double-assignment


def test_embedding_skipped_when_embedder_none_residue_kept() -> None:
    """With embedder=None the residue stays in a Drain bucket — never dropped (§8.1)."""
    calls = [_call("a", prompt="unique residue one"), _call("b", prompt="unique residue two")]
    clusters = discover_clusters(calls, embedder=None)
    assigned = sorted(mid for c in clusters for mid in c.member_ids)
    assert assigned == ["a", "b"]


def test_embedding_used_when_embedder_present() -> None:
    """An embedder, when supplied, sub-clusters the unstructured residue."""
    calls = [
        _call("a", prompt="aa"),  # len 2 -> parity 0
        _call("b", prompt="bbbb"),  # len 4 -> parity 0
        _call("c", prompt="ccc"),  # len 3 -> parity 1
    ]
    clusters = discover_clusters(calls, embedder=_StubEmbedder())
    assigned = sorted(mid for c in clusters for mid in c.member_ids)
    assert assigned == ["a", "b", "c"]  # still no drop


def test_every_cluster_unconfirmed() -> None:
    """Every discovered cluster is unconfirmed (human-confirm is onboarding, not here)."""
    calls = [_call("a", call_site="x"), _call("b", tools=("t",))]
    clusters = discover_clusters(calls, embedder=None)
    assert all(c.confirmed is False for c in clusters)


def test_cluster_carries_confidence_in_unit_interval() -> None:
    """Each cluster carries a confidence in [0, 1]."""
    calls = [_call("a", call_site="x"), _call("b", call_site="x")]
    clusters = discover_clusters(calls, embedder=None)
    assert all(0.0 <= c.confidence <= 1.0 for c in clusters)


def test_deterministic_clustering() -> None:
    """Clustering the same calls twice yields identical cluster ids and membership."""
    calls = [_call("a", call_site="x"), _call("b", call_site="x"), _call("c", call_site="y")]
    first = discover_clusters(calls, embedder=None)
    second = discover_clusters(calls, embedder=None)
    assert [(c.cluster_id, c.member_ids) for c in first] == [
        (c.cluster_id, c.member_ids) for c in second
    ]


def test_cluster_task_type_detected_structurally() -> None:
    """A cluster's task type is the structurally-detected type of its members."""
    calls = [
        _call("a", call_site="triage", prompt="Classify the ticket urgency"),
        _call("b", call_site="triage", prompt="Classify the ticket topic"),
    ]
    clusters = discover_clusters(calls, embedder=None)
    triage = next(c for c in clusters if set(c.member_ids) == {"a", "b"})
    assert triage.task_type is TaskType.CLASSIFICATION


def test_empty_input_yields_no_clusters() -> None:
    """No calls -> no clusters (a total function, no crash)."""
    assert discover_clusters([], embedder=None) == ()
