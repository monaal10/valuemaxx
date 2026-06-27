"""ATTR-0 — the system-owned tier -> confidence-label mapping (§3.1).

The mapping is system-owned: exact/deterministic -> high, candidate -> medium,
likely -> advisory. There is NO user setter — a customer can never relabel an
inferred match as high-confidence (the ``no_user_override_of_confidence_mapping``
rule).
"""

from __future__ import annotations

import pytest
from valuemaxx.attribution.confidence import scoring
from valuemaxx.core import BindingTier, ConfidenceLabel


def test_exact_maps_to_high() -> None:
    """An exact binding renders as high confidence."""
    assert scoring.label_for(BindingTier.EXACT) is ConfidenceLabel.HIGH


def test_deterministic_maps_to_high() -> None:
    """A deterministic binding renders as high confidence."""
    assert scoring.label_for(BindingTier.DETERMINISTIC) is ConfidenceLabel.HIGH


def test_candidate_maps_to_medium() -> None:
    """A candidate (entity-match) binding renders as medium confidence."""
    assert scoring.label_for(BindingTier.CANDIDATE) is ConfidenceLabel.MEDIUM


def test_likely_maps_to_advisory() -> None:
    """A likely (semantic) binding renders as advisory — never high."""
    assert scoring.label_for(BindingTier.LIKELY) is ConfidenceLabel.ADVISORY


def test_every_tier_is_mapped() -> None:
    """Every binding tier resolves to a label (the map is total)."""
    for tier in BindingTier:
        assert isinstance(scoring.label_for(tier), ConfidenceLabel)


def test_candidate_and_likely_never_map_to_high() -> None:
    """The advisory tiers never render as high confidence (honesty axis)."""
    assert scoring.label_for(BindingTier.CANDIDATE) is not ConfidenceLabel.HIGH
    assert scoring.label_for(BindingTier.LIKELY) is not ConfidenceLabel.HIGH


def test_mapping_has_no_user_setter() -> None:
    """The scoring module exposes no setter to override the system-owned mapping."""
    public = {name for name in dir(scoring) if not name.startswith("_")}
    forbidden = {"set_confidence_mapping", "set_tier_label", "update_mapping", "register_label"}
    assert public & forbidden == set()


def test_label_for_is_the_only_module_function() -> None:
    """``label_for`` is the only function the scoring module itself defines (no override path)."""
    import types

    own_functions = {
        name
        for name, obj in vars(scoring).items()
        if isinstance(obj, types.FunctionType) and obj.__module__ == scoring.__name__
    }
    assert own_functions == {"label_for"}


def test_internal_table_is_read_only() -> None:
    """The system-owned mapping cannot be mutated through the module attribute."""
    with pytest.raises(TypeError):
        scoring._TIER_TO_LABEL[BindingTier.LIKELY] = ConfidenceLabel.HIGH  # type: ignore[index]  # deliberate misuse


def test_label_for_rejects_an_unmapped_value() -> None:
    """A value outside the BindingTier vocabulary raises rather than inventing a label."""
    with pytest.raises(KeyError):
        scoring.label_for("not_a_tier")  # type: ignore[arg-type]  # deliberate misuse
