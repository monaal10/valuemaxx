"""Context propagation + the injected Protocols (H10).

``active_run_id`` is the ambient run id carried on a :class:`~contextvars.ContextVar`.
``asyncio`` tasks propagate it, but raw ``ThreadPoolExecutor.submit`` and
``os.fork``/multiprocessing do NOT (PEP 567): the SDK (G3) patches
``ThreadPoolExecutor.submit`` to wrap callables with :func:`run_in_context`.

**Fork-degrade rule (documented here, enforced at G2-ATTRIBUTION/G3):** a child
process starts with *no* ambient ``run_id`` (contextvars don't cross fork/spawn).
The SDK never guesses — an LLM call in a child without an explicitly re-established
run context is captured with its binding tier downgraded (T1 unavailable -> T2/T4)
and **labeled**, never silently mis-bound.

The injected Protocols (:class:`Clock`, :class:`UuidGen`, :class:`Rng`,
:class:`Embedder`, :class:`ProviderClient`, :class:`LlmJudge`) keep app code
deterministic and testable: no ``datetime.now()`` / ``uuid4()`` / ``random()`` in
app code — a clock/uuid/rng is injected so tests are reproducible (AGENTS.md §1).
"""

from __future__ import annotations

from contextvars import ContextVar, copy_context
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from datetime import datetime

    from valuemaxx.core.ids import RunId

active_run_id: ContextVar[RunId | None] = ContextVar("valuemaxx_active_run_id", default=None)
"""The ambient run id for the current execution context (None when unset)."""


@runtime_checkable
class Clock(Protocol):
    """An injectable clock so app code never calls ``datetime.now()`` directly."""

    def now(self) -> datetime:
        """Return the current tz-aware time."""
        ...


@runtime_checkable
class UuidGen(Protocol):
    """An injectable uuid generator so ids are reproducible under test."""

    def new(self) -> str:
        """Return a fresh unique id string."""
        ...


@runtime_checkable
class Rng(Protocol):
    """An injectable random source so sampling is reproducible under test."""

    def random(self) -> float:
        """Return a float in [0, 1)."""
        ...

    def sample(self, population: Sequence[object], k: int) -> Sequence[object]:
        """Return ``k`` items sampled from ``population``."""
        ...


@runtime_checkable
class Embedder(Protocol):
    """An injectable text embedder (used by the eval discover/cluster step)."""

    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """Return an embedding vector for each input text."""
        ...


@runtime_checkable
class ProviderClient(Protocol):
    """An injectable provider client for exact token counting + completion (eval)."""

    def count_tokens(self, *, model: str, text: str) -> int:
        """Count tokens for ``text`` under ``model`` using the provider's tokenizer."""
        ...

    def complete(self, *, model: str, prompt: str) -> str:
        """Return a completion for ``prompt`` under ``model``."""
        ...


@runtime_checkable
class LlmJudge(Protocol):
    """An injectable LLM-as-judge grader (capped at ``directional``, §8.2)."""

    def grade(self, *, prediction: str, reference: str, rubric: str) -> float:
        """Grade ``prediction`` against ``reference`` under ``rubric``; return a score."""
        ...


def run_in_context(fn: Callable[[], object], /) -> Callable[[], object]:
    """Wrap ``fn`` so it runs in a copy of the current context (carries contextvars).

    The SDK patches ``ThreadPoolExecutor.submit`` to use this so the ambient
    ``run_id`` survives the thread-pool hop (raw ``submit`` does not, PEP 567).
    """
    ctx = copy_context()
    return lambda: ctx.run(fn)


__all__ = [
    "Clock",
    "Embedder",
    "LlmJudge",
    "ProviderClient",
    "Rng",
    "UuidGen",
    "active_run_id",
    "run_in_context",
]
