"""Write the valuemaxx integration snippet INTO the user's repository.

Agents read the repo they are working in, not installed site-packages, so the
integration guidance must live in the user's own ``AGENTS.md``. ``write_agents_md``
creates or appends to ``<repo>/AGENTS.md`` a snippet that tells an agent how to wire
valuemaxx honestly: the honesty axes are system-owned, draft attribution rules via
``suggest_attribution_rule`` (unconfirmed candidates a human confirms), and validate
outcomes.yaml via ``validate_outcome_rule``. It is idempotent (a sentinel marker
prevents re-appending) and never clobbers existing content.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

# A sentinel so a second write is a no-op (idempotent append).
_MARKER = "<!-- valuemaxx:agent-integration -->"

_SNIPPET = f"""\
{_MARKER}
## valuemaxx — AI margin intelligence

This repo uses valuemaxx to measure cost-per-outcome with confidence. When wiring or
editing valuemaxx integration, honor these system-owned invariants:

- The honesty axes (binding tier, signal_class, cost provenance) are SYSTEM-OWNED.
  Never set or guess them. An inferred match is never `exact`; a successful call is
  `action_attempted`, not a confirmed outcome.
- Every rollup carries `minimum_tier` + `confidence_distribution`. Never collapse
  them into a bare number.
- To wire an attribution rule, call `suggest_attribution_rule` — it returns an
  UNCONFIRMED candidate for a human to confirm. Do not hand-write or auto-apply one.
- To check an `outcomes.yaml`, call `validate_outcome_rule`. To preview a draft,
  call `scaffold_outcome_rule` (also unconfirmed).

See the generated `llms.txt` for the full capability list.
"""


def write_agents_md(repo: Path) -> Path:
    """Create or append the valuemaxx snippet into ``<repo>/AGENTS.md`` (idempotent).

    Returns the path written. If ``AGENTS.md`` already contains the snippet marker,
    this is a no-op (idempotent); otherwise the snippet is appended without touching
    existing content.
    """
    target = repo / "AGENTS.md"
    existing = target.read_text() if target.exists() else ""
    if _MARKER in existing:
        return target
    separator = "" if existing == "" else "\n"
    target.write_text(f"{existing}{separator}{_SNIPPET}")
    return target


__all__ = ["write_agents_md"]
