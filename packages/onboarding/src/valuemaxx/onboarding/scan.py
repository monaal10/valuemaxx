"""SCAN — a read-only AST scan of a target codebase (design §7 step 1).

Parses every ``.py`` file with the stdlib :mod:`ast` module (never executes it,
never writes to it) and classifies the sites the onboarding agent needs:

* **run boundaries** — functions that contain an LLM call site (where ``init()`` /
  run instrumentation belongs);
* **outcome sites** — status setters (``x.status = ...``), ``mark_*``/``resolve``/
  ``close`` functions, ORM writes (``.save()`` / ``.commit()``), outbound external
  writes (Stripe/CRM/calendar/email), and webhook handlers;
* **durable entity ids** — parameters/attributes ending in ``_id`` that are in scope
  at a run boundary.

Every captured string (snippets, symbols) is passed through
:func:`~valuemaxx.onboarding.redact.redact` before it enters the result, so a secret
encountered in the source is never echoed into the scan output (design §7 / H12).
``detect_echoes_metadata`` consults the :data:`ECHOING_SYSTEMS` allowlist: systems
that echo injected metadata back (Stripe/HubSpot/Zendesk) support deterministic T3
binding; others (Salesforce) do not and fall back to entity matching (T4).
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING, Final

from valuemaxx.onboarding.capabilities import ScanResult, ScanSite, SiteKind
from valuemaxx.onboarding.redact import redact

if TYPE_CHECKING:
    from pathlib import Path

# Systems that echo injected metadata back on the later webhook → support T3
# deterministic binding (design §6 / §7). Salesforce et al. do not.
ECHOING_SYSTEMS: Final[frozenset[str]] = frozenset({"stripe", "hubspot", "zendesk"})

# Outbound systems whose calls are outcome-bearing external writes. The value is
# the canonical system name recorded on the site.
_EXTERNAL_SYSTEMS: Final[dict[str, str]] = {
    "stripe": "stripe",
    "hubspot": "hubspot",
    "zendesk": "zendesk",
    "salesforce": "salesforce",
    "sendgrid": "sendgrid",
    "twilio": "twilio",
    "calendar": "calendar",
}

# Attribute calls that mark a database write.
_ORM_WRITE_METHODS: Final[frozenset[str]] = frozenset({"save", "commit", "flush", "add"})

# Function-name stems that signal an outcome transition.
_MARK_PREFIXES: Final[tuple[str, ...]] = ("mark_", "resolve", "close", "complete", "finalize")

# Attribute names that look like an LLM call (run-boundary signal).
_LLM_CALL_HINTS: Final[frozenset[str]] = frozenset(
    {"complete", "completions", "create", "messages", "chat", "invoke", "generate"}
)
# Names whose constructor/call marks an LLM client at a run boundary.
_LLM_CLIENT_HINTS: Final[frozenset[str]] = frozenset(
    {"anthropic", "openai", "client", "llm", "agent"}
)


def detect_echoes_metadata(system: str) -> bool:
    """Return True iff ``system`` echoes injected metadata back (T3-capable)."""
    return system in ECHOING_SYSTEMS


def _entity_ids_in_scope(func: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[str, ...]:
    """The parameter names ending in ``_id`` (durable entity ids in scope)."""
    ids: list[str] = []
    for arg in func.args.args:
        if arg.arg.endswith("_id") and arg.arg not in ids:
            ids.append(arg.arg)
    return tuple(ids)


def _call_root_name(call: ast.Call) -> str | None:
    """The leftmost name of a call target, e.g. ``stripe`` in ``stripe.X.create(...)``."""
    node: ast.expr = call.func
    while isinstance(node, ast.Attribute):
        node = node.value
    if isinstance(node, ast.Name):
        return node.id
    return None


def _call_attr_name(call: ast.Call) -> str | None:
    """The trailing attribute of a call, e.g. ``create`` in ``stripe.X.create(...)``."""
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    if isinstance(call.func, ast.Name):
        return call.func.id
    return None


def _make_site(
    *,
    kind: SiteKind,
    file: str,
    node: ast.AST,
    symbol: str,
    source: str,
    system: str | None = None,
    echoes_metadata: bool = False,
    entity_ids: tuple[str, ...] = (),
) -> ScanSite:
    """Build a redacted :class:`ScanSite` for a node within ``source``."""
    line = getattr(node, "lineno", 0)
    snippet = redact(ast.get_source_segment(source, node) or "")
    return ScanSite(
        kind=kind,
        file=file,
        line=line,
        symbol=redact(symbol),
        snippet=snippet,
        system=system,
        echoes_metadata=echoes_metadata,
        entity_ids=entity_ids,
    )


def _scan_function(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    file: str,
    source: str,
) -> tuple[list[ScanSite], list[ScanSite], list[str]]:
    """Classify the sites inside one function. Returns (run_boundaries, outcomes, entity_ids)."""
    run_boundaries: list[ScanSite] = []
    outcomes: list[ScanSite] = []
    entity_ids = list(_entity_ids_in_scope(func))
    is_run_boundary = False

    for node in ast.walk(func):
        if isinstance(node, ast.Assign):
            outcomes.extend(_status_setter_sites(node, file=file, source=source, symbol=func.name))
        elif isinstance(node, ast.Call):
            site, boundary = _classify_call(node, file=file, source=source, symbol=func.name)
            if boundary:
                is_run_boundary = True
            if site is not None:
                outcomes.append(site)

    if _is_webhook_handler(func):
        outcomes.append(
            _make_site(
                kind="webhook_handler", file=file, node=func, symbol=func.name, source=source
            )
        )
    if _is_mark_function(func):
        outcomes.append(
            _make_site(kind="mark_function", file=file, node=func, symbol=func.name, source=source)
        )
    if is_run_boundary:
        run_boundaries.append(
            _make_site(
                kind="run_boundary",
                file=file,
                node=func,
                symbol=func.name,
                source=source,
                entity_ids=tuple(entity_ids),
            )
        )
    return run_boundaries, outcomes, entity_ids


def _status_setter_sites(
    node: ast.Assign, *, file: str, source: str, symbol: str
) -> list[ScanSite]:
    """A ``something.status = ...`` assignment is a status setter."""
    sites: list[ScanSite] = []
    for target in node.targets:
        if isinstance(target, ast.Attribute) and target.attr == "status":
            sites.append(
                _make_site(kind="status_setter", file=file, node=node, symbol=symbol, source=source)
            )
    return sites


def _classify_call(
    call: ast.Call, *, file: str, source: str, symbol: str
) -> tuple[ScanSite | None, bool]:
    """Classify a call site. Returns (site_or_None, is_llm_run_boundary)."""
    root = _call_root_name(call)
    attr = _call_attr_name(call)

    # External outbound write into a known system.
    if root is not None and root in _EXTERNAL_SYSTEMS:
        system = _EXTERNAL_SYSTEMS[root]
        site = _make_site(
            kind="external_write",
            file=file,
            node=call,
            symbol=symbol,
            source=source,
            system=system,
            echoes_metadata=detect_echoes_metadata(system),
        )
        return site, False

    # ORM write: x.save() / db.session.commit().
    if attr in _ORM_WRITE_METHODS:
        return (
            _make_site(kind="orm_write", file=file, node=call, symbol=symbol, source=source),
            False,
        )

    # LLM call boundary: a client-shaped root with an LLM-shaped method.
    is_boundary = (
        root is not None
        and root.lower() in _LLM_CLIENT_HINTS
        and (attr is None or attr in _LLM_CALL_HINTS)
    ) or (root is not None and root.lower() in _LLM_CLIENT_HINTS and attr is None)
    return None, is_boundary


def _is_webhook_handler(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Heuristic: a function whose name mentions a webhook, or takes a ``request``."""
    name = func.name.lower()
    if "webhook" in name or "callback" in name:
        return True
    return "hook" in name and any(a.arg in {"request", "payload", "event"} for a in func.args.args)


def _is_mark_function(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Heuristic: a ``mark_*`` / ``resolve`` / ``close`` style outcome function."""
    name = func.name.lower()
    return any(name.startswith(prefix) or name == prefix for prefix in _MARK_PREFIXES)


def scan_codebase(root: Path) -> ScanResult:
    """Scan every ``.py`` file under ``root`` (read-only) and classify outcome sites.

    Unparseable files are skipped with a warning (never a crash). Returns a
    :class:`ScanResult` whose every captured string has been secret-redacted.
    """
    run_boundaries: list[ScanSite] = []
    outcome_sites: list[ScanSite] = []
    entity_ids: list[str] = []
    warnings: list[str] = []

    for py in sorted(root.rglob("*.py")):
        rel = str(py.relative_to(root))
        text = py.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            warnings.append(f"skipped unparseable file {rel}: {exc.msg}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fn_boundaries, fn_outcomes, fn_entities = _scan_function(
                    node, file=rel, source=text
                )
                run_boundaries.extend(fn_boundaries)
                outcome_sites.extend(fn_outcomes)
                for eid in fn_entities:
                    if eid not in entity_ids:
                        entity_ids.append(eid)

    return ScanResult(
        run_boundaries=tuple(run_boundaries),
        outcome_sites=tuple(outcome_sites),
        entity_ids=tuple(entity_ids),
        warnings=tuple(warnings),
    )


__all__ = ["ECHOING_SYSTEMS", "detect_echoes_metadata", "scan_codebase"]
