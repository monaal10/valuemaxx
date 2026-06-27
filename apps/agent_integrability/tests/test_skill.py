"""SKILL.md tests — the Claude Code Skill references the validate/scaffold tools.

The shipped Skill must (a) exist with valid frontmatter and (b) reference the
validate/suggest tools an agent uses to wire valuemaxx honestly — so the agent is
steered to confirm rather than guess/auto-apply.
"""

from __future__ import annotations

from valuemaxx.agent_integrability import skill_path


def test_skill_file_exists() -> None:
    """The Skill ships at skill/SKILL.md."""
    assert skill_path().exists()


def test_skill_has_frontmatter() -> None:
    """The Skill has YAML frontmatter with a name + description."""
    text = skill_path().read_text()
    assert text.startswith("---")
    head = text.split("---", 2)[1]
    assert "name:" in head
    assert "description:" in head


def test_skill_references_validate_and_suggest_tools() -> None:
    """The Skill steers the agent to the validate/suggest tools (confirm, never guess)."""
    text = skill_path().read_text()
    assert "validate_outcome_rule" in text
    assert "validate_init" in text
    assert "suggest_attribution_rule" in text


def test_skill_states_axes_are_system_owned() -> None:
    """The Skill states the honesty axes are system-owned (not agent-set)."""
    lowered = skill_path().read_text().lower()
    assert "system-owned" in lowered
    assert "binding tier" in lowered
    assert "signal_class" in lowered
