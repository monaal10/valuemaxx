"""DIFF — the hunks-only, secret-free reviewable diff (design §7 step 5 / H12).

:func:`build_reviewable_diff` emits a :class:`~valuemaxx.onboarding.capabilities.\
ReviewableDiff` of bounded **hunks** — never whole files. This is the mechanical
"emit the diff, not the codebase" guarantee: the agent's only write artifact is a
small set of additive changes (an ``init()`` insert at each run boundary, plus the
generated ``outcomes.yaml``), so raw source can never be exfiltrated through the diff
path. Unmodified files contribute no hunk.

Every hunk passes :func:`~valuemaxx.onboarding.redact.assert_no_secret` before it is
returned. By default each hunk line is :func:`~valuemaxx.onboarding.redact.redact`-ed
first (defence in depth); with ``redact_first=False`` a smuggled secret instead trips
the assertion and raises :class:`~valuemaxx.onboarding.errors.SecretEncounteredError`
— proving the gate is real, not decorative.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from valuemaxx.onboarding.capabilities import DiffHunk, ReviewableDiff
from valuemaxx.onboarding.redact import assert_no_secret, redact
from valuemaxx.onboarding.render import render_outcomes_yaml

if TYPE_CHECKING:
    from valuemaxx.onboarding.capabilities import Proposal, ScanResult, ScanSite

_INIT_LINE = "import valuemaxx; valuemaxx.init()  # added by the onboarding agent"


def _init_hunk(boundary: ScanSite) -> DiffHunk:
    """An additive hunk inserting valuemaxx.init() at a run boundary."""
    line = boundary.line
    return DiffHunk(
        file=boundary.file,
        header=f"@@ -{line},0 +{line},1 @@ {boundary.symbol}",
        lines=(f"+    {_INIT_LINE}",),
    )


def _outcomes_yaml_hunk(proposal: Proposal) -> DiffHunk:
    """An additive hunk creating outcomes.yaml from the rendered proposal."""
    rendered = render_outcomes_yaml(proposal)
    body = rendered.splitlines()
    return DiffHunk(
        file="outcomes.yaml",
        header=f"@@ -0,0 +1,{len(body)} @@",
        lines=tuple(f"+{line}" for line in body),
    )


def _finalize(hunk: DiffHunk, *, redact_first: bool) -> DiffHunk:
    """Redact (or assert) a hunk's lines; raise if a secret survives the gate."""
    if redact_first:
        hunk = DiffHunk(
            file=redact(hunk.file),
            header=redact(hunk.header),
            lines=tuple(redact(line) for line in hunk.lines),
        )
    assert_no_secret(hunk.file)
    assert_no_secret(hunk.header)
    for line in hunk.lines:
        assert_no_secret(line)
    return hunk


def build_reviewable_diff(
    proposal: Proposal,
    scan: ScanResult,
    *,
    redact_first: bool = True,
) -> ReviewableDiff:
    """Build a hunks-only :class:`ReviewableDiff` (additive, bounded, secret-free).

    Emits one ``init()`` hunk per discovered run boundary plus the generated
    ``outcomes.yaml`` hunk. Each hunk is redacted (``redact_first=True``) and then
    asserted secret-free; a surviving secret raises ``SecretEncounteredError``.
    """
    hunks: list[DiffHunk] = []
    for boundary in scan.run_boundaries:
        hunks.append(_finalize(_init_hunk(boundary), redact_first=redact_first))
    hunks.append(_finalize(_outcomes_yaml_hunk(proposal), redact_first=redact_first))
    return ReviewableDiff(hunks=tuple(hunks))


__all__ = ["build_reviewable_diff"]
