"""no_auto_switch — a recommendation never auto-applies (green; owner EVAL).

The eval recommendation is **evidence for a human decision, never an auto-switch**
(§8.6): ``EvalRecommendation.auto_switch`` is ``Literal[False]`` in core, so ``True``
is structurally unrepresentable, and no eval source declares a mutable/true
auto-switch or an "apply recommendation automatically" path.

``flags_violation`` inspects a source string for the violation markers (a mutable
``auto_switch: bool``, ``auto_switch=True``/``Literal[True]``, or an auto-apply
function). The negative fixture is a synthetic module that declares a true
auto-switch; the foundation subject is the real eval report builder, which always
sets ``auto_switch=False``. ``foundation_auto_switch_violations`` scans every eval
source so the rule is a real repo-wide backstop, not just a string check.
"""

from __future__ import annotations

from tests.conformance.astutil import package_src
from tests.conformance.rulebase import Rule, RuleKind

_MARKERS: tuple[str, ...] = (
    "auto_switch: bool",
    "auto_switch=True",
    "auto_switch: Literal[True]",
    "apply_recommendation_automatically",
)


def _flags(subject: object) -> bool:
    assert isinstance(subject, str)
    return any(marker in subject for marker in _MARKERS)


def _negative_fixture() -> object:
    return "class EvalRecommendation(BaseModel):\n    auto_switch: bool = True\n"


def _foundation_subject() -> object:
    # the real eval report builder: it always constructs auto_switch=False.
    return (package_src("eval") / "report.py").read_text()


def foundation_auto_switch_violations() -> list[str]:
    """Scan every eval source; return any file declaring a true/mutable auto-switch."""
    offenders: list[str] = []
    for py in package_src("eval").rglob("*.py"):
        if "__pycache__" in py.parts:
            continue
        if _flags(py.read_text()):
            offenders.append(str(py))
    return offenders


RULE = Rule(
    name="no_auto_switch",
    kind=RuleKind.STATIC,
    green_now=True,
    owner_task="EVAL",
    flags_violation=_flags,
    negative_fixture=_negative_fixture,
    foundation_subject=_foundation_subject,
)
