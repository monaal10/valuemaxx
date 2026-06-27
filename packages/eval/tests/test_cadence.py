"""CADENCE: triggered re-eval + switching hysteresis — never on a timer (§8.7)."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest
from valuemaxx.eval.cadence import should_reeval, surface_switch_if_warranted
from valuemaxx.eval.types import CadenceTrigger

# ---------------------------------------------------------------- should_reeval


@pytest.mark.parametrize("trigger", list(CadenceTrigger))
def test_should_reeval_accepts_every_known_trigger(trigger: CadenceTrigger) -> None:
    """Each of the four cadence triggers warrants a re-eval (§8.7)."""
    assert should_reeval(trigger) is True


def test_should_reeval_rejects_unknown_trigger() -> None:
    """A trigger outside the closed CadenceTrigger vocabulary is rejected."""
    with pytest.raises(ValueError, match="trigger"):
        should_reeval("on_a_timer")  # type: ignore[arg-type]  # asserting the closed vocabulary


def test_should_reeval_has_no_timer_or_interval_param() -> None:
    """should_reeval takes ONLY a trigger — no timer/interval/schedule/cron param (§8.7)."""
    sig = inspect.signature(should_reeval)
    params = set(sig.parameters)
    assert params == {"trigger"}
    for forbidden in ("interval", "timer", "schedule", "cron", "period", "every", "seconds"):
        assert forbidden not in params


def test_cadence_module_has_no_timer_api_ast() -> None:
    """AST guard: the cadence module never references a timer/scheduler API (§8.7).

    Re-eval is triggered, never on a clock — so the module must not import or call a
    scheduler/timer (time.sleep, threading.Timer, sched, apscheduler, croniter).
    """
    src = Path(inspect.getfile(should_reeval)).read_text(encoding="utf-8")
    tree = ast.parse(src)
    banned_roots = {"sched", "apscheduler", "croniter", "schedule"}
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not (imported & banned_roots), f"cadence imports a scheduler: {imported & banned_roots}"
    # no time.sleep / Timer call anywhere
    assert "sleep" not in src
    assert "Timer" not in src


# ---------------------------------------------------------------- surface_switch_if_warranted


def test_first_recommendation_always_surfaces() -> None:
    """With no prior parity, the first recommendation always surfaces (nothing to debounce)."""
    assert surface_switch_if_warranted(new_parity=0.80, prior_parity=None) is True


def test_hysteresis_blocks_sub_15_percent_change() -> None:
    """A sub-15% relative change is blocked — no churning on noise (§8.7)."""
    # 0.80 -> 0.88 is +10% relative, below the 15% band
    assert surface_switch_if_warranted(new_parity=0.88, prior_parity=0.80) is False


def test_hysteresis_allows_15_percent_change() -> None:
    """A 15% relative change meets the hysteresis and surfaces."""
    # 1.0 -> 1.15 is exactly +15%
    assert surface_switch_if_warranted(new_parity=1.15, prior_parity=1.0) is True


def test_hysteresis_allows_large_change() -> None:
    """A large improvement clearly surfaces."""
    assert surface_switch_if_warranted(new_parity=0.95, prior_parity=0.50) is True


def test_hysteresis_symmetric_on_regression() -> None:
    """A 15%+ regression also surfaces (the recommendation is worth revisiting both ways)."""
    assert surface_switch_if_warranted(new_parity=0.80, prior_parity=1.0) is True
