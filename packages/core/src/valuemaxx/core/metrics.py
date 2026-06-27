"""MetricDefinition — the typed shape of a user-defined metric (§11).

This is the closed, typed shape the wire/storage contract needs; the full metric
grammar (allowlisted numerator/denominator tokens, the retracted-excluded
denominator semantics) is compiled in the G2 ``valuemaxx.metrics`` package. Defining
the shape here keeps it the single source of truth.
"""

from __future__ import annotations

from collections.abc import Mapping

from valuemaxx.core.base import StrictModel


class MetricDefinition(StrictModel):
    """A named metric: an allowlisted numerator over a (retracted-excluded) denominator."""

    name: str
    numerator: str
    denominator: str
    filters: Mapping[str, str]
    group_by: tuple[str, ...]


__all__ = ["MetricDefinition"]
