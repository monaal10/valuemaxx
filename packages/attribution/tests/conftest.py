"""Path bootstrap: add this tests dir to sys.path so sibling `_helpers` imports
resolve under --import-mode=importlib without a colliding `tests` package.
See AGENTS.md §5b."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
