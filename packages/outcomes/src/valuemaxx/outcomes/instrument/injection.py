"""OUT-C: T3 ``run_id`` injection — stamp the active run id into an outbound SDK call.

At ``init()`` :func:`install_run_id_injection` wraps each declared
:attr:`~valuemaxx.outcomes.schema.RunIdInjectionSpec.sdk_call` (e.g.
``stripe.PaymentIntent.create``) with a ``wrapt`` wrapper. When the host issues the
call, the wrapper reads the active ``run_id`` from :data:`~valuemaxx.core.active_run_id`
and **copy-on-write** merges it into the configured ``inject_into`` path (e.g.
``metadata.run_id``) of the outbound kwargs, so the external system echoes it back on
its later webhook — converting an impossible delayed attribution into an exact join (T3).

Two invariants:

* **Copy-on-write.** :func:`_merge_path` deep-copies only the dict *spine* along the
  inject path; the caller's own dicts are never mutated (a later read of the caller's
  ``metadata`` must not see our ``run_id``).
* **Init-ordering (H10).** If the ``sdk_call`` symbol isn't importable at ``init()``
  (lazy import, wrong order), it is recorded in :attr:`InjectionReport.unresolved` and a
  startup **warning** names it — never a silent no-op.

If there is no active run, the call passes through untouched. A host error from the
wrapped call always propagates unchanged — injection never hides it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

import wrapt
from valuemaxx.core import active_run_id
from valuemaxx.outcomes.instrument._resolve import resolve_target
from valuemaxx.outcomes.safelog import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from valuemaxx.core import RunId
    from valuemaxx.outcomes.schema import RunIdInjectionSpec

_logger = get_logger("valuemaxx.outcomes.injection")


@dataclass(frozen=True, slots=True)
class InjectionReport:
    """The result of installing run_id injection: resolved + unresolved sdk_calls."""

    installed: tuple[str, ...]
    unresolved: tuple[str, ...]


def install_run_id_injection(specs: Sequence[RunIdInjectionSpec]) -> InjectionReport:
    """Wrap each declared ``sdk_call`` to inject the active run_id; report what resolved.

    An unresolved ``sdk_call`` (not importable at init) is named in a startup warning and
    returned in :attr:`InjectionReport.unresolved` — the caller is never left guessing.
    """
    installed: list[str] = []
    unresolved: list[str] = []
    for spec in specs:
        resolved = resolve_target(spec.sdk_call)
        if resolved is None:
            _logger.warning(
                "run_id_injection sdk_call not importable at init (run_id will NOT round-trip): %s",
                spec.sdk_call,
            )
            unresolved.append(spec.sdk_call)
            continue
        wrapper = _make_injection_wrapper(spec.inject_into)
        wrapt.wrap_function_wrapper(resolved.module_name, resolved.attr_path, wrapper)
        installed.append(spec.sdk_call)
    return InjectionReport(installed=tuple(installed), unresolved=tuple(unresolved))


def _make_injection_wrapper(
    inject_into: str,
) -> Callable[
    [Callable[..., object], object, tuple[object, ...], dict[str, object]], object
]:
    path = tuple(inject_into.split("."))

    def _wrapper(
        wrapped: Callable[..., object],
        _instance: object,
        args: tuple[object, ...],
        kwargs: dict[str, object],
    ) -> object:
        run_id = active_run_id.get()
        if run_id is None:
            return wrapped(*args, **kwargs)
        merged = _merge_path(kwargs, path, run_id)
        return wrapped(*args, **merged)

    return _wrapper


def _merge_path(
    kwargs: dict[str, object], path: tuple[str, ...], run_id: RunId
) -> dict[str, object]:
    """Return a copy of ``kwargs`` with ``run_id`` set at ``path`` (copy-on-write spine).

    Only the dict nodes along ``path`` are copied; sibling values are shared by
    reference (cheap) but the caller's path dicts are never mutated. The final path
    segment is the field name; the leading segments are the nested container path.
    """
    if not path:
        return kwargs
    root: dict[str, object] = dict(kwargs)
    *containers, leaf = path
    cursor: dict[str, object] = root
    for segment in containers:
        child = _shallow_copy_node(cursor.get(segment))
        cursor[segment] = child
        cursor = child
    cursor[leaf] = str(run_id)
    return root


def _shallow_copy_node(child: object) -> dict[str, object]:
    """Copy a path node into a fresh string-keyed dict (or a new empty one if absent)."""
    if isinstance(child, dict):
        source = cast("dict[object, object]", child)
        return {str(key): value for key, value in source.items()}
    return {}


__all__ = ["InjectionReport", "install_run_id_injection"]
