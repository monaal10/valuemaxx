"""AGENTS.md writer tests — write the integration snippet INTO the user's repo.

Agents don't scan site-packages, so ``write_agents_md`` writes a valuemaxx
integration snippet into the user's own repository (creating or appending to its
``AGENTS.md``). The snippet tells the agent how to wire valuemaxx honestly: the axes
are system-owned, use ``suggest_attribution_rule``, validate with
``validate_outcome_rule``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from valuemaxx.agent_integrability.agents_md_writer import write_agents_md

if TYPE_CHECKING:
    from pathlib import Path


def test_write_agents_md_creates_file_in_user_repo(tmp_path: Path) -> None:
    """write_agents_md creates AGENTS.md in the target repo with the valuemaxx snippet."""
    written = write_agents_md(tmp_path)
    assert written == tmp_path / "AGENTS.md"
    assert written.exists()
    text = written.read_text()
    assert "valuemaxx" in text
    assert "suggest_attribution_rule" in text
    assert "system-owned" in text.lower()


def test_write_agents_md_appends_without_clobbering(tmp_path: Path) -> None:
    """If AGENTS.md already exists, the snippet is appended, not overwritten."""
    target = tmp_path / "AGENTS.md"
    target.write_text("# Existing repo guidance\n")
    write_agents_md(tmp_path)
    text = target.read_text()
    assert "Existing repo guidance" in text  # original preserved
    assert "valuemaxx" in text  # snippet appended


def test_write_agents_md_is_idempotent(tmp_path: Path) -> None:
    """Writing twice does not duplicate the snippet."""
    write_agents_md(tmp_path)
    first = (tmp_path / "AGENTS.md").read_text()
    write_agents_md(tmp_path)
    second = (tmp_path / "AGENTS.md").read_text()
    assert first == second
