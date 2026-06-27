"""Render a capability output for the terminal — a rollup never prints bare (H7).

``render_output`` formats a pydantic output model as JSON for the CLI. The honesty
rule is enforced here: if the output is *rollup-shaped* (it carries an H7
confidence) the rendered text always surfaces ``minimum_tier`` and the distribution.
A rollup is detected three ways:

* a flat ``minimum_tier`` + ``confidence_distribution`` on the model itself
  (e.g. the allocation rollup);
* a nested :class:`~valuemaxx.core.rollup.RollupConfidence` in a ``confidence``
  field;
* a tuple of cells each carrying a ``confidence`` (e.g. a metric result).

Because ``render_output`` dumps the whole model as JSON, the H7 fields are always
present in the text for a rollup; :func:`is_rollup_output` exists so a caller can
additionally assert/emphasize the headline tier and refuse to drop it.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from pydantic import BaseModel

_FLAT_H7_FIELDS = ("minimum_tier", "confidence_distribution")


def _has_flat_confidence(model: BaseModel) -> bool:
    fields = type(model).model_fields
    return all(name in fields for name in _FLAT_H7_FIELDS)


def _has_nested_confidence(model: BaseModel) -> bool:
    fields = type(model).model_fields
    if "confidence" in fields:
        return True
    # a tuple/sequence of cells each carrying a confidence (e.g. a metric result)
    for name in fields:
        value: object = getattr(model, name, None)
        if isinstance(value, tuple):
            cells = cast("tuple[object, ...]", value)
            if len(cells) > 0 and hasattr(cells[0], "confidence"):
                return True
    return False


def is_rollup_output(model: BaseModel) -> bool:
    """True iff ``model`` carries an H7 confidence (flat, nested, or per-cell)."""
    return _has_flat_confidence(model) or _has_nested_confidence(model)


def _headline_tier(model: BaseModel) -> str | None:
    """The headline ``minimum_tier`` for a rollup output, if directly present."""
    tier = getattr(model, "minimum_tier", None)
    if tier is None:
        confidence = getattr(model, "confidence", None)
        tier = getattr(confidence, "minimum_tier", None)
    if tier is None:
        return None
    return getattr(tier, "value", str(tier))


def render_output(model: BaseModel) -> str:
    """Render ``model`` as pretty JSON; a rollup always carries its minimum_tier.

    The full model is serialized (so the H7 fields are always in the text for a
    rollup), with a leading ``minimum_tier: <tier>`` headline when the model exposes
    one directly — the conservative label can never be omitted from a rollup print.
    """
    body = json.dumps(model.model_dump(mode="json"), indent=2, sort_keys=True)
    if is_rollup_output(model):
        tier = _headline_tier(model)
        if tier is not None:
            return f"minimum_tier: {tier}\n{body}"
        # nested-per-cell rollups: the cells carry minimum_tier in the JSON body,
        # which already contains both H7 fields — emit a marker so the headline is
        # unmissable even when there is no single top-level tier.
        return f"minimum_tier: (per-cell, see confidence below)\n{body}"
    return body


__all__ = ["is_rollup_output", "render_output"]
