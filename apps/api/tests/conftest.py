"""pytest bootstrap for the api app tests.

Adds this ``tests/`` directory to ``sys.path`` so test modules can ``import
_api_helpers`` by its bare, package-unique name. Per AGENTS.md §5b (test-layout
ratchet) shared helpers live in a uniquely-named non-``conftest`` module and are
NEVER imported via a global ``tests.conftest`` name — that collides across packages
under ``--import-mode=importlib`` in the combined repo run. This file defines no
fixtures; it only makes the sibling helper importable.
"""

from __future__ import annotations

import sys
from pathlib import Path

_TESTS_DIR = str(Path(__file__).resolve().parent)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)
