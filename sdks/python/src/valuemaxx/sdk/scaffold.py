"""The reversible ``init`` scaffolder (§5.1).

The scaffolder injects a single import + ``init()`` call site into the host entry
file, wrapped in unambiguous sentinel markers. ``revert`` removes exactly the
sentinel-delimited block, restoring the file byte-for-byte — the wiring is
removable without touching app logic, so an agent (or human) can undo it cleanly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

_BEGIN = "# >>> valuemaxx init (auto-scaffolded; remove with `valuemaxx scaffold revert`)\n"
_END = "# <<< valuemaxx init\n"


def _block(*, tenant_env: str, ingest_env: str) -> str:
    """The exact sentinel-delimited wiring block injected at the top of the entry file."""
    return (
        _BEGIN
        + "import os\n"
        + "import valuemaxx.sdk as valuemaxx\n"
        + "valuemaxx.init(\n"
        + f"    tenant_id=os.environ[{tenant_env!r}],\n"
        + f"    ingest_key=os.environ[{ingest_env!r}],\n"
        + '    endpoint=os.environ.get("VALUEMAXX_ENDPOINT", "https://ingest.valuemaxx.dev"),\n'
        + ")\n"
        + _END
    )


def inject(entry: Path, *, tenant_env: str, ingest_env: str) -> None:
    """Prepend the wiring block to ``entry`` (idempotent — never double-wires)."""
    original = entry.read_text()
    if _BEGIN in original:
        return  # already scaffolded
    entry.write_text(_block(tenant_env=tenant_env, ingest_env=ingest_env) + original)


def revert(entry: Path) -> None:
    """Remove the sentinel-delimited wiring block, restoring original bytes (no-op if absent)."""
    text = entry.read_text()
    start = text.find(_BEGIN)
    if start == -1:
        return  # nothing to revert
    end = text.find(_END, start)
    if end == -1:
        return  # malformed; leave untouched rather than corrupt
    end += len(_END)
    entry.write_text(text[:start] + text[end:])


__all__ = ["inject", "revert"]
