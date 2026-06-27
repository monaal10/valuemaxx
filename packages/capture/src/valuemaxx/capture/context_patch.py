"""PG5 — ThreadPoolExecutor context propagation + fork handling (H2, §5.1).

``run_id`` rides a :class:`~contextvars.ContextVar`. ``asyncio`` tasks propagate
it, but raw ``ThreadPoolExecutor.submit`` does NOT (PEP 567), so a worker thread
loses the ambient run id and any LLM call there would be mis-bound. We patch
``ThreadPoolExecutor.submit`` to run the submitted callable inside a *copy* of the
current context (``contextvars.copy_context().run(...)`` — the approach the OTel
Python SDK uses), so the run id survives the thread-pool hop. The patch is
reversible via :meth:`ContextPatchHandle.uninstall`.

**Fork boundary:** a child process starts with NO ambient run id (contextvars
don't cross ``fork``/``spawn``). We never guess — :func:`run_id_for_child` returns
``None``, signalling the caller to downgrade the binding tier and label it rather
than silently mis-bind (the fork-degrade rule documented in ``core.context``).
"""

from __future__ import annotations

import contextvars
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from concurrent.futures import Future

    from valuemaxx.core.ids import RunId

# the original unbound submit, captured once at module import so repeated
# install/uninstall cycles always restore the genuine original.
_ORIGINAL_SUBMIT = ThreadPoolExecutor.submit


class ContextPatchHandle:
    """A reversible handle over the ThreadPoolExecutor.submit context patch."""

    def __init__(self) -> None:
        self._active = True

    def uninstall(self) -> None:
        """Restore the original ``ThreadPoolExecutor.submit`` (idempotent)."""
        if not self._active:
            return
        ThreadPoolExecutor.submit = _ORIGINAL_SUBMIT  # reversible monkeypatch (PG5)
        self._active = False


def install_threadpool_context_propagation() -> ContextPatchHandle:
    """Patch ``ThreadPoolExecutor.submit`` to carry the current context into workers.

    Returns a :class:`ContextPatchHandle` whose ``uninstall`` reverts the patch.
    Installing is safe to repeat — the original ``submit`` is captured once at
    import, so any uninstall restores the genuine original.
    """

    def _context_submit(
        self: ThreadPoolExecutor,
        fn: Callable[..., object],
        /,
        *args: object,
        **kwargs: object,
    ) -> Future[object]:
        ctx = contextvars.copy_context()

        def _run() -> object:
            return fn(*args, **kwargs)

        return _ORIGINAL_SUBMIT(self, ctx.run, _run)

    ThreadPoolExecutor.submit = _context_submit  # reversible monkeypatch (PG5)
    return ContextPatchHandle()


def run_id_for_child(*, parent_run_id: RunId) -> RunId | None:
    """Return the run id a forked child should bind to — always ``None`` (H2).

    contextvars don't cross ``fork``/``spawn``, so the child has no ambient run
    context. We never copy the parent's id across the boundary (that would silently
    mis-bind every child LLM call); the caller must re-establish the run context
    explicitly, and any call without it is captured with its binding tier
    downgraded and labelled.
    """
    return None


__all__ = [
    "ContextPatchHandle",
    "install_threadpool_context_propagation",
    "run_id_for_child",
]
