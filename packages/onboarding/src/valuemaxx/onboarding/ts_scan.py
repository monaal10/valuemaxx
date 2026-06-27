"""TypeScript/JavaScript scanning for the onboarding agent.

valuemaxx ships a TS SDK, so onboarding must work on TS/JS codebases — not just
Python. This module parses ``.ts/.tsx/.js/.mjs/.cjs`` files with **tree-sitter**
(a real AST, never executing the code) and emits the same :class:`ScanSite` shape
the Python scanner does, so ``build_proposal``/``render`` are language-agnostic.

What it finds, for Vercel-AI-SDK-style code:

* **run boundaries** — calls to ``generateText`` / ``streamText`` / ``generateObject``
  (the ``ai`` package) and provider setup (``createOpenAI`` / ``createAnthropic`` /
  ``createGoogleGenerativeAI``). These are where ``init()`` + the tracer wire in.
* **outcome sites** — status-setter assignments (``x.status = "resolved"``),
  ``mark*/resolve/close/complete`` calls, ORM/db writes (``.save()``/``.update()``/
  ``.insert()``), and outbound calls to known echoing systems (Stripe/HubSpot/…).
* **entity ids in scope** — ``*Id`` / ``*_id`` identifiers (conversationId,
  customerId, applicationId).

Every captured string passes :func:`~valuemaxx.onboarding.redact.redact`, so a
secret in a real ``.env``-adjacent literal never lands in a result.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from valuemaxx.onboarding.capabilities import ScanSite
from valuemaxx.onboarding.redact import redact
from valuemaxx.onboarding.scan import ECHOING_SYSTEMS

if TYPE_CHECKING:
    from tree_sitter import Node

# Vercel AI SDK call names that mark an LLM run boundary.
_TS_LLM_CALLS: Final[frozenset[str]] = frozenset(
    {"generateText", "streamText", "generateObject", "streamObject", "embed"}
)
# Provider-setup calls that also mark a run boundary (model construction).
_TS_PROVIDER_CALLS: Final[frozenset[str]] = frozenset(
    {"createOpenAI", "createAnthropic", "createGoogleGenerativeAI", "createGateway"}
)
# Method names that mark a database write.
_TS_ORM_WRITES: Final[frozenset[str]] = frozenset(
    {"save", "update", "insert", "create", "upsert", "delete"}
)
# Function/method-name stems that signal an outcome transition.
_TS_MARK_PREFIXES: Final[tuple[str, ...]] = (
    "mark",
    "resolve",
    "close",
    "complete",
    "finalize",
)
TS_SUFFIXES: Final[tuple[str, ...]] = (".ts", ".tsx", ".js", ".mjs", ".cjs", ".jsx")


def is_ts_source(suffix: str) -> bool:
    """Return True iff ``suffix`` (incl. dot) is a TS/JS source extension."""
    return suffix in TS_SUFFIXES


def _text(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", "replace")


def _callee_name(call: Node, source: bytes) -> str | None:
    """The simple name being called: ``foo(...)`` -> ``foo``; ``a.b.foo(...)`` -> ``foo``."""
    fn = call.child_by_field_name("function")
    if fn is None:
        return None
    if fn.type == "identifier":
        return _text(fn, source)
    if fn.type == "member_expression":
        prop = fn.child_by_field_name("property")
        if prop is not None:
            return _text(prop, source)
    return None


def _enclosing_symbol(node: Node, source: bytes) -> str:
    """Best-effort name of the function/method enclosing ``node`` (for the site symbol)."""
    cur: Node | None = node.parent
    while cur is not None:
        if cur.type in {
            "function_declaration",
            "method_definition",
            "generator_function_declaration",
        }:
            name = cur.child_by_field_name("name")
            if name is not None:
                return _text(name, source)
        if cur.type in {"variable_declarator"} and cur.child_by_field_name("value") is not None:
            value = cur.child_by_field_name("value")
            if value is not None and value.type in {"arrow_function", "function_expression"}:
                name = cur.child_by_field_name("name")
                if name is not None:
                    return _text(name, source)
        cur = cur.parent
    return "<module>"


def _line_of(node: Node) -> int:
    return node.start_point[0] + 1


def _entity_ids_in_file(root: Node, source: bytes) -> list[str]:
    """Collect ``*Id`` / ``*_id`` identifiers used in the file (in-scope entity keys)."""
    ids: list[str] = []
    stack: list[Node] = [root]
    while stack:
        n = stack.pop()
        if n.type == "identifier":
            name = _text(n, source)
            low = name.lower()
            looks_like_id = (low.endswith("id") and len(name) > 2) or low.endswith("_id")
            if looks_like_id and name not in ids and name not in {"uuid", "guid"}:
                ids.append(name)
        stack.extend(n.children)
    return ids


def _site(
    *, kind: str, file: str, node: Node, source: bytes, system: str | None = None
) -> ScanSite:
    return ScanSite(
        kind=kind,  # type: ignore[arg-type]  # validated against SiteKind by pydantic
        file=file,
        line=_line_of(node),
        symbol=redact(_enclosing_symbol(node, source)),
        snippet=redact(_text(node, source))[:200],
        system=system,
        echoes_metadata=(system in ECHOING_SYSTEMS) if system else False,
    )


def _system_for_call(call: Node, source: bytes) -> str | None:
    """If the call's receiver names a known echoing system, return it (Stripe/…)."""
    fn = call.child_by_field_name("function")
    if fn is None or fn.type != "member_expression":
        return None
    obj = fn.child_by_field_name("object")
    if obj is None:
        return None
    receiver = _text(obj, source).lower()
    for system in ECHOING_SYSTEMS:
        if system in receiver:
            return system
    return None


def scan_ts_source(text: str, *, file: str) -> tuple[list[ScanSite], list[ScanSite], list[str]]:
    """Parse one TS/JS file. Returns (run_boundaries, outcome_sites, entity_ids).

    Never executes the code; never raises on a parse error (tree-sitter is
    error-tolerant). Lazy-imports tree-sitter so the dependency is only needed
    when a TS file is actually scanned.
    """
    import tree_sitter_typescript as tsts
    from tree_sitter import Language, Parser

    parser = Parser(Language(tsts.language_typescript()))
    source = text.encode("utf-8")
    tree = parser.parse(source)
    root = tree.root_node

    run_boundaries: list[ScanSite] = []
    outcome_sites: list[ScanSite] = []

    stack: list[Node] = [root]
    while stack:
        n = stack.pop()
        if n.type == "call_expression":
            name = _callee_name(n, source)
            if name in _TS_LLM_CALLS or name in _TS_PROVIDER_CALLS:
                run_boundaries.append(_site(kind="run_boundary", file=file, node=n, source=source))
            elif name in _TS_ORM_WRITES:
                outcome_sites.append(
                    _site(
                        kind="external_write",
                        file=file,
                        node=n,
                        source=source,
                        system=_system_for_call(n, source),
                    )
                )
            elif name is not None and any(name.lower().startswith(p) for p in _TS_MARK_PREFIXES):
                outcome_sites.append(_site(kind="mark_function", file=file, node=n, source=source))
            else:
                system = _system_for_call(n, source)
                if system is not None:
                    outcome_sites.append(
                        _site(
                            kind="external_write", file=file, node=n, source=source, system=system
                        )
                    )
        elif n.type == "assignment_expression":
            left = n.child_by_field_name("left")
            if left is not None and left.type == "member_expression":
                prop = left.child_by_field_name("property")
                if prop is not None and _text(prop, source) == "status":
                    outcome_sites.append(
                        _site(kind="status_setter", file=file, node=n, source=source)
                    )
        stack.extend(n.children)

    entity_ids = _entity_ids_in_file(root, source)
    return run_boundaries, outcome_sites, entity_ids
