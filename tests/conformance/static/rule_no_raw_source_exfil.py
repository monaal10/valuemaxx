"""no_raw_source_exfil — onboarding emits diffs, never whole source off-box (ONBOARDING-green).

The onboarding agent's "emit a diff, not the codebase" guarantee is mechanical (design
§7 / H12): its GitHub-App surface has read-only repo access and a single diff-only write
path, and it exposes NO tool that transmits raw file contents off-box. This rule encodes
that as an AST/string check:

* ``flags_violation`` flags a source that pairs a whole-file read (``open(...).read()`` /
  ``read_text()`` / ``whole_file``) with an off-box transmit (``upload`` / ``transmit`` /
  ``requests.post`` / ``httpx`` / ``exfiltrate``) — i.e. raw source leaving the box.
* the foundation subject is the real onboarding ``github_app.py`` source, which has the
  off-box boundary but no transmit-of-raw-source path, so it is NOT flagged.

``foundation_has_no_source_exfil`` scans every onboarding module for the violation, so
the whole package — not just one file — is asserted clean.
"""

from __future__ import annotations

from tests.conformance.astutil import package_src
from tests.conformance.rulebase import Rule, RuleKind

# A whole-file read (the source content) ...
_READ_MARKERS: tuple[str, ...] = ("open(", ".read()", "read_text(", "whole_file")
# ... paired with an off-box transmit is an exfil path.
_TRANSMIT_MARKERS: tuple[str, ...] = (
    "upload",
    "transmit",
    "exfiltrate",
    "requests.post",
    "requests.put",
    "httpx.",
    "urlopen",
)


def _flags(subject: object) -> bool:
    assert isinstance(subject, str)
    reads_raw = any(marker in subject for marker in _READ_MARKERS)
    transmits = any(marker in subject for marker in _TRANSMIT_MARKERS)
    return reads_raw and transmits


def _negative_fixture() -> object:
    return "upload(open(path).read())  # whole-file exfil\n"


def _foundation_subject() -> object:
    # The real onboarding off-box boundary: read-only repo access + diff-only PR write,
    # with no transmit-of-raw-source path.
    return (package_src("onboarding") / "github_app.py").read_text()


def foundation_has_no_source_exfil() -> list[str]:
    """Scan every onboarding module; return files that pair a raw read with a transmit."""
    offenders: list[str] = []
    for py in package_src("onboarding").rglob("*.py"):
        if _flags(py.read_text()):
            offenders.append(str(py))
    return offenders


RULE = Rule(
    name="no_raw_source_exfil",
    kind=RuleKind.STATIC,
    green_now=True,
    owner_task="ONBOARDING",
    flags_violation=_flags,
    negative_fixture=_negative_fixture,
    foundation_subject=_foundation_subject,
)
