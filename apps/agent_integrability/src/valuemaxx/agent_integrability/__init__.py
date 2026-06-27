"""valuemaxx.agent_integrability — the agent-integration affordances (G4).

Ships everything an LLM agent needs to integrate valuemaxx honestly:

- :func:`build_default_registry` / discovery — the canonical capability registry
  every surface projects from;
- :func:`generate_llms_txt` — the generated ``llms.txt`` index of every capability +
  the system-owned-axes instructions;
- :func:`write_agents_md` — writes the integration snippet INTO the user's repo;
- :func:`register_scaffold_caps` — the ``scaffold_*`` / ``validate_*`` MCP tools that
  return UNCONFIRMED drafts (a human confirms; never auto-applied);
- the per-framework ``examples/`` (each a runnable snippet + a validating
  outcomes.yaml), located via :func:`examples_dir`;
- the Claude Code Skill at ``skill/SKILL.md``.
"""

from __future__ import annotations

from pathlib import Path

from valuemaxx.agent_integrability.agents_md_writer import write_agents_md
from valuemaxx.agent_integrability.discovery import (
    DEFAULT_CAPABILITY_MODULES,
    KNOWN_DUPLICATE_NAMES,
    build_default_registry,
    register_modules,
)
from valuemaxx.agent_integrability.llms_txt import generate_llms_txt
from valuemaxx.agent_integrability.scaffold_caps import register_scaffold_caps


def examples_dir() -> Path:
    """The directory of per-framework integration examples shipped in this package."""
    return Path(__file__).resolve().parent / "examples"


def skill_path() -> Path:
    """The path to the shipped Claude Code Skill (``skill/SKILL.md``)."""
    return Path(__file__).resolve().parent / "skill" / "SKILL.md"


__all__ = [
    "DEFAULT_CAPABILITY_MODULES",
    "KNOWN_DUPLICATE_NAMES",
    "build_default_registry",
    "examples_dir",
    "generate_llms_txt",
    "register_modules",
    "register_scaffold_caps",
    "skill_path",
    "write_agents_md",
]
