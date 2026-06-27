"""REGISTER: project the eval funnel onto the capability registry (§3, §8)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from valuemaxx.capabilities import Mode, Registry, Surface
from valuemaxx.eval.capabilities import (
    DiscoverAgentsInput,
    EvalNotWiredError,
    bind_runtime,
    register,
)

_EXPECTED = {"discover_agents", "run_eval_funnel", "get_recommendation", "approve_gate"}


def _registry() -> Registry:
    reg = Registry()
    register(reg)
    return reg


# ---------------------------------------------------------------- register


def test_register_adds_all_four_capabilities() -> None:
    """register adds exactly the four eval capabilities (discover/run/get/approve)."""
    names = {spec.name for spec in _registry().all()}
    assert names == _EXPECTED


def test_run_eval_funnel_is_async_job() -> None:
    """The full funnel is a long-running async_job (job_id + status poll), not request/response."""
    spec = next(s for s in _registry().all() if s.name == "run_eval_funnel")
    assert spec.mode is Mode.ASYNC_JOB


def test_discover_agents_is_request_response() -> None:
    """discover_agents is a synchronous request/response capability."""
    spec = next(s for s in _registry().all() if s.name == "discover_agents")
    assert spec.mode is Mode.REQUEST_RESPONSE


def test_get_recommendation_includes_notify_surface() -> None:
    """get_recommendation is projected onto NOTIFY (digests) as well as API/MCP/CLI."""
    spec = next(s for s in _registry().all() if s.name == "get_recommendation")
    assert Surface.NOTIFY in spec.surfaces


def test_approve_gate_is_request_response() -> None:
    """approve_gate (the human cost-gate sign-off) is request/response."""
    spec = next(s for s in _registry().all() if s.name == "approve_gate")
    assert spec.mode is Mode.REQUEST_RESPONSE


def test_every_capability_has_description_and_examples() -> None:
    """Every capability carries a non-empty description and at least one example (§3)."""
    for spec in _registry().all():
        assert spec.description.strip()
        assert len(spec.examples) >= 1


def test_register_is_idempotent_per_registry() -> None:
    """Registering twice on the SAME registry raises (no silent duplicate)."""
    from valuemaxx.capabilities import DuplicateCapabilityError

    reg = Registry()
    register(reg)
    try:
        register(reg)
    except DuplicateCapabilityError:
        pass
    else:  # pragma: no cover - the assertion below makes intent explicit
        raise AssertionError("re-registering on the same registry should raise")


# ---------------------------------------------------------------- wiring (late-bound runtime)


def test_handler_before_bind_runtime_raises() -> None:
    """Invoking a handler before the EvalService is bound raises, never silently no-ops."""
    reg = Registry()
    register(reg)
    handler = next(s for s in reg.all() if s.name == "discover_agents").handler
    with pytest.raises(EvalNotWiredError, match="not wired"):
        handler(DiscoverAgentsInput(call_sites=(), prompts=()))


def test_bind_runtime_without_register_raises() -> None:
    """bind_runtime on a registry that never registered the eval caps raises (no holder)."""
    reg = Registry()
    with pytest.raises(EvalNotWiredError, match="call register"):
        bind_runtime(reg, service=None)  # type: ignore[arg-type]  # exercising the missing-holder guard


# ---------------------------------------------------------------- import discipline


def test_eval_imports_no_surface_or_store() -> None:
    """AST: NO eval source imports fastapi/typer/mcp, a concrete store, or tiktoken (§3).

    A logic package must not know how it is served, must not import a concrete store,
    and must never import tiktoken for cost. Scans every eval source file.
    """
    banned_roots = {"fastapi", "typer", "mcp", "tiktoken"}
    banned_modules = {"valuemaxx.store"}
    eval_src = Path(register.__code__.co_filename).resolve().parent
    offenders: list[str] = []
    for py in eval_src.rglob("*.py"):
        if "__pycache__" in py.parts:
            continue
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            roots: set[str] = set()
            modules: set[str] = set()
            if isinstance(node, ast.Import):
                for alias in node.names:
                    roots.add(alias.name.split(".")[0])
                    modules.add(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots.add(node.module.split(".")[0])
                modules.add(node.module)
            if roots & banned_roots or any(
                m == b or m.startswith(f"{b}.") for m in modules for b in banned_modules
            ):
                offenders.append(f"{py.name}: {sorted(roots | modules)}")
    assert not offenders, f"eval imports a forbidden surface/store/tiktoken: {offenders}"
