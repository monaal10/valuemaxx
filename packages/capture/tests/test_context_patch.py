"""PG5 — ThreadPoolExecutor copy_context patch + fork handling for run_id (H2, §5.1).

Raw ``ThreadPoolExecutor.submit`` does NOT propagate contextvars (PEP 567), so a
worker thread loses the ambient ``run_id``. We patch ``submit`` to wrap the
callable with ``copy_context().run(...)`` (the OTel approach) so the run id
survives the thread-pool hop. The patch is reversible.

Fork handling: a child process starts with no ambient ``run_id`` (contextvars
don't cross fork) — we never guess; ``run_id_for_child`` returns None so the
caller degrades the binding tier and labels it, never silently mis-binds.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from valuemaxx.capture.context_patch import (
    install_threadpool_context_propagation,
    run_id_for_child,
)
from valuemaxx.core.context import active_run_id
from valuemaxx.core.ids import RunId


def _read_active_run_id() -> RunId | None:
    return active_run_id.get()


def test_raw_threadpool_loses_run_id_without_patch() -> None:
    """test_raw_threadpool_loses_run_id_without_patch: baseline — submit drops the contextvar."""
    token = active_run_id.set(RunId("run-main"))
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(_read_active_run_id).result()
    finally:
        active_run_id.reset(token)
    # raw submit does not carry the contextvar into the worker thread
    assert result is None


def test_patched_threadpool_propagates_run_id() -> None:
    """test_patched_threadpool_propagates_run_id: after the patch, run_id survives the hop."""
    handle = install_threadpool_context_propagation()
    try:
        token = active_run_id.set(RunId("run-main"))
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                result = pool.submit(_read_active_run_id).result()
        finally:
            active_run_id.reset(token)
        assert result == RunId("run-main")  # the contextvar crossed the thread hop
    finally:
        handle.uninstall()


def test_patch_is_reversible() -> None:
    """test_patch_is_reversible: uninstall restores the original submit (loses run_id again)."""
    handle = install_threadpool_context_propagation()
    handle.uninstall()
    token = active_run_id.set(RunId("run-main"))
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(_read_active_run_id).result()
    finally:
        active_run_id.reset(token)
    assert result is None  # back to raw behaviour after uninstall


def _add(a: int, b: int) -> int:
    return a + b


def test_patch_does_not_break_submit_args_and_result() -> None:
    """test_patch_does_not_break_submit_args_and_result: submit still passes args + returns."""
    handle = install_threadpool_context_propagation()
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(_add, 2, 3).result()
        assert result == 5
    finally:
        handle.uninstall()


def test_fork_child_has_no_ambient_run_id() -> None:
    """test_fork_child_has_no_ambient_run_id: a child must re-establish context; we never guess."""
    # contextvars don't cross fork/spawn; run_id_for_child reflects that honestly.
    assert run_id_for_child(parent_run_id=RunId("run-parent")) is None


def test_install_is_idempotent() -> None:
    """test_install_is_idempotent: installing twice still restores cleanly."""
    h1 = install_threadpool_context_propagation()
    h2 = install_threadpool_context_propagation()
    h2.uninstall()
    h1.uninstall()
    token = active_run_id.set(RunId("run-main"))
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(_read_active_run_id).result()
    finally:
        active_run_id.reset(token)
    assert result is None  # fully uninstalled
