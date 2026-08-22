"""Configuration identity from parsed request structure.

System prompts are templates with short interpolated slots.  A rolling longest-common
subsequence recovers the stable template without pretending that the varying values
are configuration.  When too little survives, identity explicitly falls back to the
caller-supplied request structure and is marked weak.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from valuemaxx.core.optimization import ConfigIdentity

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from valuemaxx.core.optimization import OptimizationConfig

_WEAK_THRESHOLD = Decimal("0.3")


@dataclass(frozen=True, slots=True)
class InferredTemplate:
    """The recovered stable text and how much of the observed prompt it explains."""

    template: str
    strength: Decimal
    weak: bool


def infer_system_template(
    messages: Sequence[str],
    *,
    structure: Sequence[str] = ("system",),
    weak_threshold: Decimal = _WEAK_THRESHOLD,
    max_samples: int = 30,
) -> InferredTemplate:
    """Infer a system template by rolling LCS over a bounded, distributed sample.

    Callers supply messages already sampled across time and run ids.  The function
    bounds work to ``max_samples`` and, when more are supplied, takes evenly-spaced
    observations rather than the first consecutive burst.
    """
    if max_samples <= 0:
        raise ValueError("max_samples must be positive")
    selected = _spread_sample(tuple(messages), max_samples)
    if not selected:
        return _weak_fallback(structure)

    template = selected[0]
    for message in selected[1:]:
        template = _lcs(template, message)
        if not template:
            break
    denominator = max(len(message) for message in selected)
    strength = Decimal(len(template)) / Decimal(denominator) if denominator else Decimal(0)
    if strength < weak_threshold:
        return _weak_fallback(structure, strength=strength)
    return InferredTemplate(template=template, strength=strength, weak=False)


def compute_config_identity(
    *,
    system_messages: Sequence[str],
    tools: Sequence[Mapping[str, object]],
    config: OptimizationConfig,
    structure: Sequence[str] = ("system",),
) -> ConfigIdentity:
    """Hash system template, tools and serving parameters independently."""
    inferred = infer_system_template(system_messages, structure=structure)
    canonical_tools = sorted(
        (_canonical_json(tool) for tool in tools),
    )
    return ConfigIdentity(
        system_hash=_sha(inferred.template),
        tools_hash=_sha("\n".join(canonical_tools)),
        params_hash=_sha(config.model_dump_json(exclude_none=False)),
        template_strength=inferred.strength,
    )


def _spread_sample(messages: tuple[str, ...], limit: int) -> tuple[str, ...]:
    if len(messages) <= limit:
        return messages
    if limit == 1:
        return (messages[-1],)
    last = len(messages) - 1
    indexes = tuple(round(i * last / (limit - 1)) for i in range(limit))
    return tuple(messages[index] for index in indexes)


def _weak_fallback(structure: Sequence[str], *, strength: Decimal = Decimal(0)) -> InferredTemplate:
    canonical = "structure:" + "|".join(structure)
    return InferredTemplate(template=canonical, strength=strength, weak=True)


def _lcs(left: str, right: str) -> str:
    """A true LCS using Hirschberg's linear-space reconstruction algorithm."""
    if left == right:
        return left
    if not left or not right:
        return ""
    if len(left) == 1:
        return left if left in right else ""
    midpoint = len(left) // 2
    prefix = _lcs_lengths(left[:midpoint], right)
    suffix = _lcs_lengths(left[midpoint:][::-1], right[::-1])
    split = max(range(len(right) + 1), key=lambda j: prefix[j] + suffix[len(right) - j])
    return _lcs(left[:midpoint], right[:split]) + _lcs(left[midpoint:], right[split:])


def _lcs_lengths(left: str, right: str) -> list[int]:
    previous = [0] * (len(right) + 1)
    for left_char in left:
        current = [0]
        for index, right_char in enumerate(right, start=1):
            if left_char == right_char:
                current.append(previous[index - 1] + 1)
            else:
                current.append(max(previous[index], current[-1]))
        previous = current
    return previous


def _canonical_json(value: Mapping[str, object]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


__all__ = ["InferredTemplate", "compute_config_identity", "infer_system_template"]
