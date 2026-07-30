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


def test_skill_requires_human_approval_before_wiring() -> None:
    """The Skill must gate FILE EDITS on human approval, not just outcome rules.

    The approval language originally applied only to `outcomes.yaml` — the capture-wiring
    step just said "add init()", so an agent following it went straight to editing a
    stranger's production LLM call path. Observed in practice: a proposed one-file change
    silently became a five-file signature change while threading a handle through
    intermediate layers.
    """
    lowered = skill_path().read_text().lower()
    assert "approval gate" in lowered or "approval gates" in lowered
    # The gate must bind the WIRING step, not only the outcomes step.
    assert "before writing capture wiring" in lowered
    # Scope growth mid-change must send the agent back to the human.
    assert "stop and re-ask" in lowered


def test_skill_forbids_destructive_git_and_weakening_host_settings() -> None:
    """An integrating agent is a guest in someone else's working tree."""
    lowered = skill_path().read_text().lower()
    assert "destructive git" in lowered
    assert "minimum-release-age" in lowered
