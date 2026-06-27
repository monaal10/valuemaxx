"""DISCOVER: Drain templatization — hash the prompt SKELETON, not the filled string."""

from __future__ import annotations

from valuemaxx.eval.drain import skeleton_hash, templatize


def test_templatize_masks_numeric_literals() -> None:
    """Numbers are masked to a wildcard so two filled prompts share one skeleton."""
    a = templatize("Order #123 is late by 4 days")
    b = templatize("Order #987 is late by 12 days")
    assert a == b
    assert "<NUM>" in a


def test_templatize_masks_emails_and_urls() -> None:
    """High-cardinality literals (emails, urls) are masked, not kept."""
    a = templatize("Contact alice@example.com at https://a.example.com/x")
    b = templatize("Contact bob@other.org at https://b.other.org/y")
    assert a == b


def test_templatize_preserves_structural_words() -> None:
    """Structural (non-literal) tokens survive — the skeleton keeps the shape."""
    out = templatize("Classify this ticket: order 5 late")
    assert "Classify" in out
    assert "ticket" in out


def test_skeleton_hash_ignores_literals() -> None:
    """Two prompts differing only in literals hash identically (skeleton, not string)."""
    h1 = skeleton_hash("Refund order 111 for user 222")
    h2 = skeleton_hash("Refund order 999 for user 888")
    assert h1 == h2


def test_skeleton_hash_differs_on_structure() -> None:
    """Prompts with different skeletons hash differently."""
    h1 = skeleton_hash("Classify ticket 5")
    h2 = skeleton_hash("Summarize document 5")
    assert h1 != h2


def test_skeleton_hash_is_deterministic() -> None:
    """The same prompt hashes to the same value every time (no salt/randomness)."""
    assert skeleton_hash("Order 7 shipped") == skeleton_hash("Order 7 shipped")


def test_skeleton_hash_is_stable_hex() -> None:
    """The hash is a stable hex digest (content-addressable, not Python's salted hash)."""
    h = skeleton_hash("Order 7 shipped")
    assert isinstance(h, str)
    assert len(h) == 64  # sha256 hex
    int(h, 16)  # parses as hex
