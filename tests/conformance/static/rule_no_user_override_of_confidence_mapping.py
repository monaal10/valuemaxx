"""no_user_override_of_confidence_mapping — the tier->label map is system-owned.

Owner ATTRIBUTION (now GREEN). The binding-tier -> confidence-label mapping is
system-owned and total; there is no user setter (§3.1). A customer can never relabel
an inferred (candidate/likely) match as high-confidence. The only public surface of
the scoring module is the pure ``label_for`` function.

``flags_violation`` flags source that exposes a setter for the mapping (the negative
fixture). The foundation subject is the real ``confidence/scoring.py`` source.
``foundation_scoring_exposes_no_setter`` additionally exercises the live module:
its only public callable is ``label_for`` and the table is read-only.
"""

from __future__ import annotations

from tests.conformance.astutil import package_src
from tests.conformance.rulebase import Rule, RuleKind

_MARKERS: tuple[str, ...] = ("set_confidence_mapping", "TIER_LABELS.update", "def set_tier_label")


def _flags(subject: object) -> bool:
    assert isinstance(subject, str)
    return any(marker in subject for marker in _MARKERS)


def _negative_fixture() -> object:
    return "def set_confidence_mapping(user_map): TIER_LABELS.update(user_map)\n"


def _foundation_subject() -> object:
    # The real scoring module exposes only the pure ``label_for`` function.
    return (package_src("attribution") / "confidence" / "scoring.py").read_text()


def foundation_scoring_exposes_no_setter() -> list[str]:
    """Exercise the live module: return any public mutation surface (should be empty).

    The scoring module must define exactly one public function (``label_for``) and
    its tier->label table must be read-only (no public setter, no mutable table).
    """
    import types

    from valuemaxx.attribution.confidence import scoring

    offenders: list[str] = []
    own_functions = {
        name
        for name, obj in vars(scoring).items()
        if isinstance(obj, types.FunctionType) and obj.__module__ == scoring.__name__
    }
    if own_functions != {"label_for"}:
        offenders.append(f"unexpected public functions: {sorted(own_functions)}")

    # The system-owned table must reject mutation (it is a MappingProxyType).
    from valuemaxx.core import BindingTier, ConfidenceLabel

    try:
        scoring._TIER_TO_LABEL[BindingTier.LIKELY] = ConfidenceLabel.HIGH  # type: ignore[index]
        offenders.append("tier->label table is mutable")
    except TypeError:
        pass
    return offenders


RULE = Rule(
    name="no_user_override_of_confidence_mapping",
    kind=RuleKind.STATIC,
    green_now=True,
    owner_task="ATTRIBUTION",
    flags_violation=_flags,
    negative_fixture=_negative_fixture,
    foundation_subject=_foundation_subject,
)
