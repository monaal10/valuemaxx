"""Shipped webhook mappings, one YAML file per provider.

The receiver in :mod:`valuemaxx.outcomes.webhook` already verifies a signature, walks
a JSON path for the run id, and falls back to entity keys. What it cannot know is that
a Stripe ``checkout.session.completed`` keeps its id at
``data.object.metadata.vmx_run_id`` and its money at ``data.object.amount_total``.
That knowledge is per provider, it is pure data, and without it every user
reverse-engineers the same handful of paths out of provider documentation.

**Adding a provider is adding one file.** Drop ``<name>.yaml`` in this directory and it
is discovered — there is no registry to edit, no import to add, and
``test_providers.py`` will immediately hold it to the same contract as the others:
every rule must be able to bind to a run, revenue outcomes must extract a value, and
a refund must be a retraction rather than a confirmation.

The templates are a starting point, not a policy. A host whose Stripe metadata key is
``order_ref`` rather than ``vmx_run_id`` copies the file and edits one line; nothing
here is privileged over a rule they write themselves.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from valuemaxx.outcomes.loader import load_rules
from valuemaxx.outcomes.predicate import SafePredicateValidator

if TYPE_CHECKING:
    from collections.abc import Sequence

    from valuemaxx.outcomes.schema import OutcomeRule

_DIR = Path(__file__).parent

#: Provider names shipped with valuemaxx, discovered from the directory rather than
#: listed here — a hand-maintained list is a second source of truth that drifts the
#: first time someone adds a file and forgets the import.
PROVIDERS: tuple[str, ...] = tuple(sorted(p.stem for p in _DIR.glob("*.yaml")))


def load_provider_rules(name: str) -> Sequence[OutcomeRule]:
    """The outcome rules a shipped provider template declares.

    Parsed through the same loader a user's own ``valuemaxx.outcomes.yaml`` goes
    through — including its AST allowlist — so a shipped template can express nothing
    a hand-written rule could not, and cannot smuggle in an expression the safe loader
    would reject from anyone else.
    """
    path = _DIR / f"{name}.yaml"
    if not path.is_file():
        raise KeyError(f"unknown provider {name!r}; shipped providers: {', '.join(PROVIDERS)}")
    return load_rules(path.read_text(), validator=SafePredicateValidator())


__all__ = ["PROVIDERS", "load_provider_rules"]
