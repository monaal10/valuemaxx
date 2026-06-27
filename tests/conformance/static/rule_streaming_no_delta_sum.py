"""streaming_no_delta_sum — never sum streaming usage deltas; take terminal (GREEN; CAPTURE).

Summing the per-``message_delta`` usage fields (output / cache tokens) instead of
taking the terminal value is the ``@langchain/anthropic`` 2x cache double-count
bug class (§5.2). This rule AST-scans a source for *token accumulation*: a ``+=``
or ``sum(...)`` whose operand references a streaming-usage token field
(``usage``, ``output_tokens``, ``cache_read``, ``cache_creation``, etc.). A bare
counter increment (``self._thinking_blocks += 1`` over a literal) is NOT flagged —
it counts blocks, it does not sum usage tokens.

Authored RED-but-meaningful, now GREEN: ``flags_violation`` flags the negative
fixture (the langchain bug pattern); the foundation subject is the real capture
streaming path (``valuemaxx.capture``'s ``terminal.py``), which overwrites the
terminal value and never sums deltas.
"""

from __future__ import annotations

import ast

from tests.conformance.astutil import package_src
from tests.conformance.rulebase import Rule, RuleKind

# token-bearing names that must never be *summed* across streaming deltas
_USAGE_TOKENS: frozenset[str] = frozenset(
    {
        "usage",
        "output_tokens",
        "completion_tokens",
        "cache_read",
        "cache_read_input_tokens",
        "cache_creation",
        "cache_creation_input_tokens",
        "ephemeral_5m_input_tokens",
        "ephemeral_1h_input_tokens",
    }
)


def _references_usage_token(node: ast.AST) -> bool:
    """True if the AST subtree references a streaming-usage token field by name."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Attribute) and sub.attr in _USAGE_TOKENS:
            return True
        if isinstance(sub, ast.Name) and sub.id in _USAGE_TOKENS:
            return True
        # mapping access like chunk["usage"]["output_tokens"]
        if (
            isinstance(sub, ast.Constant)
            and isinstance(sub.value, str)
            and sub.value in _USAGE_TOKENS
        ):
            return True
    return False


def _sums_streaming_usage(source: str) -> bool:
    """True if ``source`` sums streaming usage tokens (``+=`` or ``sum(...)`` over usage)."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        # `acc += <expr referencing usage tokens>`
        if (
            isinstance(node, ast.AugAssign)
            and isinstance(node.op, ast.Add)
            and _references_usage_token(node.value)
        ):
            return True
        # `sum(<comprehension / iterable referencing usage tokens>)`
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "sum"
            and any(_references_usage_token(arg) for arg in node.args)
        ):
            return True
    return False


def _flags(subject: object) -> bool:
    assert isinstance(subject, str)
    return _sums_streaming_usage(subject)


def _negative_fixture() -> object:
    # the langchain 2x bug: summing cache tokens across deltas instead of terminal
    return "total = sum(chunk.usage.cache_read for chunk in deltas)\n"


def _foundation_subject() -> object:
    # the real capture streaming accumulators: terminal value, never delta-sum.
    return (package_src("capture") / "terminal.py").read_text()


RULE = Rule(
    name="streaming_no_delta_sum",
    kind=RuleKind.STATIC,
    green_now=True,
    owner_task="CAPTURE",
    flags_violation=_flags,
    negative_fixture=_negative_fixture,
    foundation_subject=_foundation_subject,
)
