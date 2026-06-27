"""The system-owned binding-tier -> confidence-label mapping (§3.1, ATTR-0).

The displayed confidence of a binding is derived purely from its system-owned
:class:`~valuemaxx.core.BindingTier`:

    ``exact`` / ``deterministic`` -> ``high``
    ``candidate``                 -> ``medium``
    ``likely``                    -> ``advisory``

This mapping is **system-owned and total**. There is deliberately NO setter: a
customer cannot relabel an inferred (``candidate``/``likely``) match as
high-confidence. The only public surface is the pure function :func:`label_for`
(the ``no_user_override_of_confidence_mapping`` conformance rule asserts no
override path exists).
"""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING

from valuemaxx.core import BindingTier, ConfidenceLabel

if TYPE_CHECKING:
    from collections.abc import Mapping

# System-owned, read-only mapping. Wrapped in MappingProxyType so the table itself
# cannot be mutated through the module attribute — there is no write path at all.
_TIER_TO_LABEL: Mapping[BindingTier, ConfidenceLabel] = MappingProxyType(
    {
        BindingTier.EXACT: ConfidenceLabel.HIGH,
        BindingTier.DETERMINISTIC: ConfidenceLabel.HIGH,
        BindingTier.CANDIDATE: ConfidenceLabel.MEDIUM,
        BindingTier.LIKELY: ConfidenceLabel.ADVISORY,
    }
)


def label_for(tier: BindingTier) -> ConfidenceLabel:
    """Return the system-owned confidence label for a binding ``tier``.

    The mapping is total over :class:`~valuemaxx.core.BindingTier`; a value that is
    not a member raises :class:`KeyError` rather than inventing a label.
    """
    return _TIER_TO_LABEL[tier]


__all__ = ["label_for"]
