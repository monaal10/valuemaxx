"""Pytest bootstrap for the reconciliation test suite.

This directory is intentionally NOT a package (no ``__init__.py``) so its
``conftest`` registers under a path-unique name and several packages' suites can run
together without the ``tests.conftest`` plugin-name collision (AGENTS.md §5b).

Under ``--import-mode=importlib`` pytest does not put a test file's own directory on
``sys.path``, so this conftest adds it — letting the test modules share helpers via a
plain ``import _helpers`` (a module, not a ``conftest``, not a domain package).
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
