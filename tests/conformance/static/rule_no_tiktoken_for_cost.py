"""no_tiktoken_for_cost — tiktoken is banned in cost paths (green; foundation + CAPTURE).

tiktoken undercounts Claude (~12%), so it must never be imported for cost. The
ruff banned-api enforces this repo-wide; this conformance rule is the AST backstop.
``flags_violation`` inspects a source string; the negative fixture imports tiktoken;
the foundation subject is the real capture cost-math path (``valuemaxx.capture``'s
``pricing.py``). ``foundation_tiktoken_imports`` scans EVERY package source, so the
capture side is covered by the same repo-wide scan.
"""

from __future__ import annotations

from tests.conformance.astutil import PACKAGES_DIR, imported_roots, package_src
from tests.conformance.rulebase import Rule, RuleKind


def _flags(subject: object) -> bool:
    assert isinstance(subject, str)
    return "tiktoken" in imported_roots(subject)


def _negative_fixture() -> object:
    return "import tiktoken\nenc = tiktoken.get_encoding('cl100k_base')\n"


def _foundation_subject() -> object:
    # the real capture cost-math path: it must never import tiktoken for cost.
    return (package_src("capture") / "pricing.py").read_text()


def foundation_tiktoken_imports() -> list[str]:
    """Scan all package sources; return any file importing tiktoken."""
    offenders: list[str] = []
    for py in PACKAGES_DIR.rglob("*.py"):
        if "__pycache__" in py.parts:
            continue
        if "tiktoken" in imported_roots(py.read_text()):
            offenders.append(str(py))
    return offenders


RULE = Rule(
    name="no_tiktoken_for_cost",
    kind=RuleKind.STATIC,
    green_now=True,
    owner_task="CAPTURE",  # capture cost-math path is the cost owner; foundation already clean
    flags_violation=_flags,
    negative_fixture=_negative_fixture,
    foundation_subject=_foundation_subject,
)
