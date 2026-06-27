"""Example tests — every shipped example outcomes.yaml validates; snippets init.

Each per-framework example ships an ``outcomes.yaml`` (one outcome) and a runnable
~30-line snippet. The contract: every shipped ``outcomes.yaml`` parses + validates
through the real outcomes loader (safe predicate allowlist), and every snippet calls
``valuemaxx.init()`` (the one-line init).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from valuemaxx.agent_integrability import examples_dir
from valuemaxx.outcomes.loader import load_rules
from valuemaxx.outcomes.predicate import SafePredicateValidator

if TYPE_CHECKING:
    from pathlib import Path

_EXAMPLES = examples_dir()
_FRAMEWORKS = ("fastapi_langchain", "openai", "anthropic")


def test_examples_dir_exists() -> None:
    """The examples directory is shipped inside the package."""
    assert _EXAMPLES.is_dir()


@pytest.mark.parametrize("framework", _FRAMEWORKS)
def test_example_outcomes_yaml_validates(framework: str) -> None:
    """Each example's outcomes.yaml parses + validates through the real loader."""
    yaml_path = _EXAMPLES / framework / "outcomes.yaml"
    assert yaml_path.exists(), f"missing outcomes.yaml for {framework}"
    rules = load_rules(yaml_path.read_text(), validator=SafePredicateValidator())
    assert len(rules) == 1, f"{framework} example must declare exactly one outcome"


def test_all_shipped_outcomes_yaml_validate() -> None:
    """Every outcomes.yaml anywhere under examples/ validates (no broken sample ships)."""
    yaml_files = sorted(_EXAMPLES.rglob("outcomes.yaml"))
    assert yaml_files, "no example outcomes.yaml found"
    for yaml_path in yaml_files:
        rules = load_rules(yaml_path.read_text(), validator=SafePredicateValidator())
        assert rules, f"{yaml_path} produced no rules"


@pytest.mark.parametrize("framework", _FRAMEWORKS)
def test_example_snippet_calls_init(framework: str) -> None:
    """Each example snippet calls valuemaxx.init() (the one-line install)."""
    snippet = (_EXAMPLES / framework / "app.py").read_text()
    assert "valuemaxx.init(" in snippet, f"{framework} snippet must call valuemaxx.init()"


@pytest.mark.parametrize("framework", _FRAMEWORKS)
def test_example_snippet_is_concise(framework: str) -> None:
    """Each example snippet is a focused ~30-line demo (not a sprawling app)."""
    lines = (_EXAMPLES / framework / "app.py").read_text().splitlines()
    code_lines = [ln for ln in lines if ln.strip() and not ln.strip().startswith("#")]
    assert len(code_lines) <= 45, f"{framework} snippet should stay concise"


def test_openai_example_has_run_id_injection() -> None:
    """The OpenAI (Stripe webhook) example declares run_id injection (T3 path)."""
    yaml_path: Path = _EXAMPLES / "openai" / "outcomes.yaml"
    rules = load_rules(yaml_path.read_text(), validator=SafePredicateValidator())
    assert rules[0].run_id_injection is not None
