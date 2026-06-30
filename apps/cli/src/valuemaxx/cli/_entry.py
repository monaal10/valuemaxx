"""The ``valuemaxx`` console-script entry point — a thin, dependency-light wrapper.

The real CLI (:mod:`valuemaxx.cli.main`) imports typer / uvicorn / fastapi / the server
at module load, so importing it at all fails when the CLI's extra deps are absent (a
bare ``pip install valuemaxx`` without ``[cli]``). If the entry point pointed straight at
``valuemaxx.cli.main:main``, that failure surfaces as a raw ``ModuleNotFoundError: No
module named 'typer'`` traceback — confusing, and it looks like a bug rather than a
missing-extra.

So the published entry point targets THIS module's :func:`main`, which imports the real
CLI lazily inside a guard and, on a missing CLI dependency, prints a single actionable
line (``pip install "valuemaxx[cli]"``) and exits non-zero — never a stack trace.
"""

from __future__ import annotations

import sys

# Third-party packages the `[cli]` extra provides; a missing one of these (not a bug in
# our code) means the user installed the bare SDK without the CLI extra.
_CLI_EXTRA_MODULES = frozenset({"typer", "uvicorn", "fastapi", "pydantic_settings", "sqlalchemy"})


def main() -> None:
    """Run the CLI, or print an install hint if the ``[cli]`` extra is missing."""
    try:
        from valuemaxx.cli.main import main as _real_main
    except ModuleNotFoundError as exc:
        missing = exc.name or ""
        # Only translate a MISSING-CLI-EXTRA import error into the friendly hint; a real
        # bug (some other module missing) re-raises so it isn't silently swallowed.
        if missing.split(".")[0] in _CLI_EXTRA_MODULES:
            sys.stderr.write(
                f"valuemaxx: the CLI needs the '[cli]' extra (missing dependency "
                f"'{missing}').\n"
                f'Install it with:  pip install "valuemaxx[cli]"\n'
            )
            raise SystemExit(1) from exc
        raise
    _real_main()


__all__ = ["main"]
