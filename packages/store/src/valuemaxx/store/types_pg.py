"""Cross-dialect column types — JSONB on Postgres, JSON elsewhere.

Postgres is the one supported production store (§9), and its ``JSONB`` is the
load-bearing type for the raw-record replay payloads and the outcome ``raw`` map:
it preserves arbitrary nested structure and indexes match-keys. Unit tests,
however, run driver-agnostically (SQLite) where ``JSONB`` does not exist. SQLAlchemy's
:func:`~sqlalchemy.types.TypeEngine.with_variant` lets one column declaration bind
``JSONB`` for the ``postgresql`` dialect and fall back to the generic ``JSON`` for
all others, so the *same* table metadata drives both the real-Postgres fidelity
tests and the fast unit tests without a second schema.

Money is :class:`~sqlalchemy.Numeric` ``(20, 10)`` everywhere (never ``Float``):
binary floats cannot represent decimal cents exactly, so a money column must round
through base-10 fixed precision to match the ``Decimal`` domain values (M7).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import JSON, Numeric
from sqlalchemy.dialects.postgresql import JSONB

if TYPE_CHECKING:
    from decimal import Decimal

    from sqlalchemy.types import TypeEngine

# Fixed-precision decimal money: 20 total digits, 10 after the point. Wide enough
# for any realistic per-event or aggregate USD figure without ever touching float.
_MONEY_PRECISION = 20
_MONEY_SCALE = 10


def jsonb() -> TypeEngine[object]:
    """A fresh JSON column type: ``JSONB`` on Postgres, generic ``JSON`` elsewhere.

    A new instance per call keeps each column's type state independent (SQLAlchemy
    attaches per-column processing state to the type object, so types are not shared).
    """
    return JSON().with_variant(JSONB(), "postgresql")


def money() -> Numeric[Decimal]:
    """A fresh ``NUMERIC(20, 10)`` money column type (never ``Float``, M7)."""
    return Numeric(precision=_MONEY_PRECISION, scale=_MONEY_SCALE, asdecimal=True)


__all__ = ["jsonb", "money"]
