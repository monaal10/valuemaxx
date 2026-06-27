"""G1-CORE-CONTEXT: active_run_id ContextVar + injected Protocols (H10)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from valuemaxx.core.context import (
    Clock,
    Embedder,
    LlmJudge,
    ProviderClient,
    Rng,
    UuidGen,
    active_run_id,
    run_in_context,
)
from valuemaxx.core.ids import RunId


def test_active_run_id_default_none() -> None:
    """test_active_run_id_default_none: the ambient run id defaults to None."""
    assert active_run_id.get() is None


def test_run_in_context_carries_run_id_across_thread() -> None:
    """run_in_context carries the contextvar across a ThreadPoolExecutor; raw submit does NOT."""
    token = active_run_id.set(RunId("run-xyz"))
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            # raw submit: the worker thread does NOT see the ambient run id (PEP 567)
            raw = pool.submit(active_run_id.get).result()
            assert raw is None
            # run_in_context: the worker DOES see it (copy_context().run)
            carried = pool.submit(run_in_context(active_run_id.get)).result()
            assert carried == RunId("run-xyz")
    finally:
        active_run_id.reset(token)


class _ClockImpl:
    def now(self) -> datetime:
        return datetime(2026, 6, 27, tzinfo=UTC)


class _UuidImpl:
    def new(self) -> str:
        return "uuid-1"


class _RngImpl:
    def random(self) -> float:
        return 0.5

    def sample(self, population: list[object], k: int) -> list[object]:
        return population[:k]


class _EmbedderImpl:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] for _ in texts]


class _ProviderImpl:
    def count_tokens(self, *, model: str, text: str) -> int:
        return len(text)

    def complete(self, *, model: str, prompt: str) -> str:
        return prompt


class _JudgeImpl:
    def grade(self, *, prediction: str, reference: str, rubric: str) -> float:
        return 1.0


def test_protocols_runtime_checkable() -> None:
    """test_protocols_runtime_checkable: each injected Protocol is runtime-checkable."""
    assert isinstance(_ClockImpl(), Clock)
    assert isinstance(_UuidImpl(), UuidGen)
    assert isinstance(_RngImpl(), Rng)
    assert isinstance(_EmbedderImpl(), Embedder)
    assert isinstance(_ProviderImpl(), ProviderClient)
    assert isinstance(_JudgeImpl(), LlmJudge)


def test_non_conforming_object_is_not_an_instance() -> None:
    assert not isinstance(object(), Clock)
