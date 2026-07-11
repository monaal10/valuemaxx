"""OUT-C/T2: W3C-baggage ``run_id`` producer — carry the active run id across a live hop.

At ``init()`` :func:`install_run_id_baggage` wraps each declared outbound HTTP client call
(e.g. ``httpx.Client.request``) with a ``wrapt`` wrapper. When the host issues the call
inside an established run, the wrapper reads the active ``run_id`` from
:data:`~valuemaxx.core.active_run_id` and **copy-on-write** merges a
``valuemaxx.run_id=<id>`` member into the outbound W3C ``baggage`` header, so the receiving
service's ingress can parse it back into the cascade's baggage map and bind ``exact`` (T2).

This is the sibling of :func:`~valuemaxx.outcomes.instrument.injection.install_run_id_injection`:
same contextvar source, same copy-on-write / fail-open / unresolved-warns invariants — it
only targets the ``headers`` kwarg (W3C-baggage-encoded) instead of an SDK-call metadata path.

Invariants:

* **Copy-on-write.** The caller's own ``headers`` dict is never mutated — a later read of
  the caller's headers must not see our baggage member.
* **List-merge, not clobber.** An existing ``baggage`` header keeps its other members; our
  key is appended (or replaced in place if already present), per the W3C list format.
* **Init-ordering (H10).** A ``target`` that isn't importable at ``init()`` is recorded in
  :attr:`~valuemaxx.outcomes.instrument.injection.InjectionReport.unresolved` and named in a
  startup warning — never a silent no-op.

If there is no active run, the call passes through untouched. A host error from the wrapped
call always propagates unchanged — the producer never hides it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import wrapt
from valuemaxx.core import active_run_id
from valuemaxx.core.wire import BAGGAGE_RUN_ID_KEY
from valuemaxx.outcomes.instrument._resolve import resolve_target
from valuemaxx.outcomes.instrument.injection import InjectionReport
from valuemaxx.outcomes.safelog import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from valuemaxx.core import RunId

_logger = get_logger("valuemaxx.outcomes.baggage")

_HEADERS_KWARG = "headers"
_BAGGAGE_HEADER = "baggage"


def install_run_id_baggage(targets: Sequence[str]) -> InjectionReport:
    """Wrap each declared HTTP ``target`` to stamp the active run_id onto W3C baggage.

    An unresolved ``target`` (not importable at init) is named in a startup warning and
    returned in :attr:`InjectionReport.unresolved` — the caller is never left guessing.
    """
    installed: list[str] = []
    unresolved: list[str] = []
    for target in targets:
        resolved = resolve_target(target)
        if resolved is None:
            _logger.warning(
                "run_id baggage target not importable at init (run_id will NOT ride baggage): %s",
                target,
            )
            unresolved.append(target)
            continue
        wrapt.wrap_function_wrapper(resolved.module_name, resolved.attr_path, _wrapper)
        installed.append(target)
    return InjectionReport(installed=tuple(installed), unresolved=tuple(unresolved))


def _wrapper(
    wrapped: Callable[..., object],
    _instance: object,
    args: tuple[object, ...],
    kwargs: dict[str, object],
) -> object:
    run_id = active_run_id.get()
    if run_id is None:
        return wrapped(*args, **kwargs)
    merged = _merge_baggage(kwargs, run_id)
    return wrapped(*args, **merged)


def _merge_baggage(kwargs: dict[str, object], run_id: RunId) -> dict[str, object]:
    """Return a copy of ``kwargs`` with run_id merged into the W3C ``baggage`` header.

    Copy-on-write: only the ``kwargs`` dict and its ``headers`` dict are copied; the
    caller's own headers dict is never mutated. Existing baggage members are preserved;
    our key is replaced in place if already present (no duplicate member).
    """
    root: dict[str, object] = dict(kwargs)
    headers = _shallow_copy_headers(root.get(_HEADERS_KWARG))
    headers[_BAGGAGE_HEADER] = _with_run_id_member(headers.get(_BAGGAGE_HEADER), run_id)
    root[_HEADERS_KWARG] = headers
    return root


def _shallow_copy_headers(headers: object) -> dict[str, object]:
    """Copy the headers kwarg into a fresh string-keyed dict (or a new empty one if absent)."""
    if isinstance(headers, dict):
        source = cast("dict[object, object]", headers)
        return {str(key): value for key, value in source.items()}
    return {}


def _with_run_id_member(existing: object, run_id: RunId) -> str:
    """Build the W3C baggage value: existing members (minus a stale run_id) + ours."""
    members: list[str] = []
    if isinstance(existing, str) and existing.strip():
        members = [
            member.strip()
            for member in existing.split(",")
            if member.strip() and not member.strip().startswith(f"{BAGGAGE_RUN_ID_KEY}=")
        ]
    members.append(f"{BAGGAGE_RUN_ID_KEY}={run_id}")
    return ",".join(members)


__all__ = ["install_run_id_baggage"]
