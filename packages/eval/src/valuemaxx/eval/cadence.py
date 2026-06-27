"""CADENCE — triggered re-eval + switching hysteresis, never on a timer (§8.7).

Re-evaluation is **triggered, never on a clock**: a new model release, cost drift,
latency drift, or a newly-discovered agent. There is deliberately no timer / interval
/ schedule parameter anywhere in this module — :func:`should_reeval` takes only a
:class:`~valuemaxx.eval.types.CadenceTrigger`, and a conformance/AST test asserts no
scheduler API is referenced.

Surfacing a switch is debounced by a **15% hysteresis**: a change must clear the band
(``|new - old| / |old| >= 0.15``) to surface, which prevents churning the
recommendation on noise. The very first recommendation (no prior) always surfaces.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from valuemaxx.eval.stats import meets_hysteresis

if TYPE_CHECKING:
    from valuemaxx.eval.types import CadenceTrigger

_HYSTERESIS = 0.15


def should_reeval(trigger: CadenceTrigger) -> bool:
    """Whether a re-eval is warranted by ``trigger`` — only the four triggers (§8.7).

    Accepts only a member of the closed :class:`~valuemaxx.eval.types.CadenceTrigger`
    vocabulary; there is NO timer/interval parameter, because re-eval is triggered,
    never scheduled.

    Raises:
        ValueError: if ``trigger`` is not a known :class:`CadenceTrigger`.
    """
    # Defend the boundary against an out-of-vocabulary value coming from an untyped
    # caller (a surface/CLI string). Membership in the enum's values is the closed
    # check; isinstance would be statically redundant for a typed caller.
    from valuemaxx.eval.types import CadenceTrigger as _Trigger

    valid = {t.value for t in _Trigger}
    if getattr(trigger, "value", trigger) not in valid:
        raise ValueError(
            f"unknown cadence trigger {trigger!r}; re-eval is triggered (not timed) and "
            f"must be one of {sorted(valid)}"
        )
    return True


def surface_switch_if_warranted(*, new_parity: float, prior_parity: float | None) -> bool:
    """Whether a switch should surface given the prior parity — 15% hysteresis (§8.7).

    The first recommendation (``prior_parity is None``) always surfaces — there is
    nothing to debounce. Otherwise the change must clear the 15% hysteresis band
    (symmetric: a large improvement OR regression surfaces), so the recommendation
    never churns on sub-threshold noise.
    """
    if prior_parity is None:
        return True
    return meets_hysteresis(new=new_parity, old=prior_parity, threshold=_HYSTERESIS)


__all__ = ["should_reeval", "surface_switch_if_warranted"]
