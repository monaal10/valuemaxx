"""GITHUB-APP — read-only scan + write-to-PR-branch-only model (design §7 / H12).

The optional server-side execution mode runs as a GitHub App scoped to
``contents: read`` + ``pull_requests: write`` only. The "emit a diff, not the
codebase" guarantee is **mechanical, not intentional**: :class:`ReadOnlyGithubApp`
exposes exactly two repo-touching operations —

* :meth:`ReadOnlyGithubApp.read_file` — reads a file **in-process** (the scanner
  needs source to parse); the content never leaves the box through this object, and
* :meth:`ReadOnlyGithubApp.open_pr` — opens a PR whose body carries ONLY the bounded
  :class:`~valuemaxx.onboarding.capabilities.ReviewableDiff` hunks, never raw file
  contents.

There is deliberately **no** ``push`` / ``write_file`` / ``transmit_contents`` /
``upload`` method — the type has no tool that can exfiltrate raw source off-box (the
``no_raw_source_exfil`` guardrail). :meth:`ReadOnlyGithubApp.assert_scopes` rejects
any scope outside :data:`ALLOWED_SCOPES`, and :meth:`open_pr` runs the diff through
:func:`~valuemaxx.onboarding.redact.assert_no_secret` before it opens.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from valuemaxx.onboarding.capabilities import PullRequest
from valuemaxx.onboarding.errors import GithubScopeError
from valuemaxx.onboarding.redact import assert_no_secret

if TYPE_CHECKING:
    from collections.abc import Mapping

    from valuemaxx.onboarding.capabilities import ReviewableDiff

# The only scopes the server-side onboarding GitHub App may hold (H12).
ALLOWED_SCOPES: Final[frozenset[str]] = frozenset({"contents:read", "pull_requests:write"})


class ReadOnlyGithubApp:
    """A GitHub App with a read-only repo surface and a diff-only write surface.

    Construct with the in-process file map the scanner reads. The object exposes no
    method that can write to the repo or transmit raw file contents off-box; its only
    write path is :meth:`open_pr`, which carries the reviewable diff and nothing else.
    """

    def __init__(self, repo_files: Mapping[str, str]) -> None:
        self._repo_files = dict(repo_files)

    def assert_scopes(self, scopes: frozenset[str]) -> None:
        """Raise :class:`GithubScopeError` if ``scopes`` exceeds the allowed envelope."""
        excess = scopes - ALLOWED_SCOPES
        if excess:
            raise GithubScopeError(
                f"requested scopes {sorted(excess)} exceed the read-only / PR-write "
                f"envelope {sorted(ALLOWED_SCOPES)}"
            )

    def read_file(self, path: str) -> str:
        """Read a repo file IN-PROCESS (for the scanner). Returns '' for a missing path."""
        return self._repo_files.get(path, "")

    def open_pr(self, *, branch: str, title: str, diff: ReviewableDiff) -> PullRequest:
        """Open a PR on ``branch`` whose body is ONLY the diff hunks (no raw source).

        Every hunk line is asserted secret-free first; a surviving secret raises
        :class:`~valuemaxx.onboarding.errors.SecretEncounteredError`. The body is built
        purely from the diff — repo file contents are never embedded.
        """
        body_lines: list[str] = []
        for hunk in diff.hunks:
            assert_no_secret(hunk.file)
            assert_no_secret(hunk.header)
            body_lines.append(f"--- {hunk.file}")
            body_lines.append(hunk.header)
            for line in hunk.lines:
                assert_no_secret(line)
                body_lines.append(line)
        return PullRequest(branch=branch, title=title, body="\n".join(body_lines))


__all__ = ["ALLOWED_SCOPES", "ReadOnlyGithubApp"]
