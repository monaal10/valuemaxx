"""SDK — the scaffolder's edits are reversible (byte-identical revert, §5.1).

The ``init`` scaffolder injects a single import + call site into the host entry
file; ``revert`` removes exactly those edits, restoring the file byte-for-byte.
Reversibility means an agent (or human) can undo the wiring without touching app
logic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from valuemaxx.sdk import scaffold

if TYPE_CHECKING:
    from pathlib import Path


def test_scaffold_then_revert_is_byte_identical(tmp_path: Path) -> None:
    """test_scaffold_then_revert_is_byte_identical: revert restores the original bytes."""
    entry = tmp_path / "main.py"
    original = 'import os\n\n\ndef main() -> None:\n    print("hello")\n'
    entry.write_text(original)

    scaffold.inject(entry, tenant_env="VALUEMAXX_TENANT", ingest_env="VALUEMAXX_KEY")
    assert entry.read_text() != original  # the scaffold added the wiring

    scaffold.revert(entry)
    assert entry.read_text() == original  # byte-for-byte restoration


def test_scaffold_injects_import_and_call(tmp_path: Path) -> None:
    """test_scaffold_injects_import_and_call: the wiring is a single import + init() call."""
    entry = tmp_path / "app.py"
    entry.write_text("def main() -> None:\n    pass\n")
    scaffold.inject(entry, tenant_env="VALUEMAXX_TENANT", ingest_env="VALUEMAXX_KEY")
    text = entry.read_text()
    assert "valuemaxx" in text
    assert "init(" in text


def test_scaffold_is_idempotent(tmp_path: Path) -> None:
    """test_scaffold_is_idempotent: injecting twice does not double-wire."""
    entry = tmp_path / "svc.py"
    entry.write_text("def main() -> None:\n    pass\n")
    scaffold.inject(entry, tenant_env="VALUEMAXX_TENANT", ingest_env="VALUEMAXX_KEY")
    once = entry.read_text()
    scaffold.inject(entry, tenant_env="VALUEMAXX_TENANT", ingest_env="VALUEMAXX_KEY")
    assert entry.read_text() == once  # no second injection


def test_revert_without_scaffold_is_noop(tmp_path: Path) -> None:
    """test_revert_without_scaffold_is_noop: reverting an un-scaffolded file changes nothing."""
    entry = tmp_path / "plain.py"
    original = "def main() -> None:\n    pass\n"
    entry.write_text(original)
    scaffold.revert(entry)
    assert entry.read_text() == original
