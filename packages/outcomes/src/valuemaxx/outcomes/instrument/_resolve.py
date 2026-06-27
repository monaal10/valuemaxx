"""Symbol resolution for wrapt patching — shared by function rules and run_id injection.

A declared target like ``stripe.PaymentIntent.create`` or ``myapp.loans.update_status``
is split into the importable *module path*, the *qualified attribute path* within that
module, and the final *attribute name* that ``wrapt`` wraps. Resolution is best-effort:
if the module/attribute isn't importable at ``init()`` (lazy import, wrong order), the
caller is told via a return value so it can emit a startup warning — it never raises and
never silently no-ops (the H10 init-ordering rule, §6.1).
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ResolvedTarget:
    """A successfully resolved patch target.

    ``module_name`` is the importable module; ``attr_path`` is the dotted path *within*
    that module that ``wrapt.wrap_function_wrapper`` patches (e.g. ``PaymentIntent.create``).
    """

    module_name: str
    attr_path: str


def resolve_target(dotted: str) -> ResolvedTarget | None:
    """Resolve ``dotted`` to a (module, attr_path) pair, or None if not importable now.

    Tries successively shorter module prefixes so both ``pkg.mod.func`` and
    ``pkg.mod.Class.method`` resolve. Returns None when no prefix imports or the
    attribute path doesn't exist on the imported module — the caller warns.
    """
    parts = dotted.split(".")
    if len(parts) < 2:
        return None
    # Try the longest importable module prefix first (so Class.method stays as attr_path).
    for split in range(len(parts) - 1, 0, -1):
        module_name = ".".join(parts[:split])
        attr_path = ".".join(parts[split:])
        module = _try_import(module_name)
        if module is not None and _has_attr_path(module, attr_path):
            return ResolvedTarget(module_name=module_name, attr_path=attr_path)
    return None


def _try_import(module_name: str) -> object | None:
    try:
        return importlib.import_module(module_name)
    except ImportError:
        return None


def _has_attr_path(root: object, attr_path: str) -> bool:
    current = root
    for attr in attr_path.split("."):
        if not hasattr(current, attr):
            return False
        current = getattr(current, attr)
    return True


__all__ = ["ResolvedTarget", "resolve_target"]
