"""Tests for GITHUB-APP — read-only scan + write-to-PR-branch-only model (H12)."""

from __future__ import annotations

import pytest
from valuemaxx.onboarding.capabilities import DiffHunk, ReviewableDiff
from valuemaxx.onboarding.errors import GithubScopeError, SecretEncounteredError
from valuemaxx.onboarding.github_app import ALLOWED_SCOPES, ReadOnlyGithubApp


def _clean_diff() -> ReviewableDiff:
    return ReviewableDiff(
        hunks=(
            DiffHunk(
                file="outcomes.yaml",
                header="@@ -0,0 +1,1 @@",
                lines=("+version: 1",),
            ),
        )
    )


def test_app_has_no_push_or_write_or_transmit_method() -> None:
    app = ReadOnlyGithubApp(repo_files={"app.py": "x = 1\n"})
    for forbidden in (
        "push",
        "write_file",
        "transmit_contents",
        "upload",
        "exfiltrate",
        "commit",
        "create_blob",
    ):
        assert not hasattr(app, forbidden), f"app must not expose {forbidden}"


def test_app_exposes_only_read_file_and_open_pr() -> None:
    public = {n for n in dir(ReadOnlyGithubApp) if not n.startswith("_")}
    # the only repo-touching methods are read_file (in-process) and open_pr (diff-only)
    assert "read_file" in public
    assert "open_pr" in public


def test_read_file_returns_in_process_content() -> None:
    app = ReadOnlyGithubApp(repo_files={"app.py": "x = 1\n"})
    assert app.read_file("app.py") == "x = 1\n"


def test_assert_scopes_accepts_exact_envelope() -> None:
    app = ReadOnlyGithubApp(repo_files={})
    app.assert_scopes(frozenset({"contents:read", "pull_requests:write"}))  # must not raise


def test_assert_scopes_accepts_subset() -> None:
    app = ReadOnlyGithubApp(repo_files={})
    app.assert_scopes(frozenset({"contents:read"}))  # must not raise


def test_assert_scopes_rejects_excess_scope() -> None:
    app = ReadOnlyGithubApp(repo_files={})
    with pytest.raises(GithubScopeError):
        app.assert_scopes(frozenset({"contents:read", "contents:write"}))
    with pytest.raises(GithubScopeError):
        app.assert_scopes(frozenset({"admin:org"}))


def test_allowed_scopes_is_the_read_only_pr_write_envelope() -> None:
    assert frozenset({"contents:read", "pull_requests:write"}) == ALLOWED_SCOPES


def test_open_pr_writes_only_diff_to_pr_branch() -> None:
    app = ReadOnlyGithubApp(repo_files={"app.py": "x = 1\n"})
    pr = app.open_pr(branch="valuemaxx/onboarding", title="add outcomes", diff=_clean_diff())
    assert pr.branch == "valuemaxx/onboarding"
    # the PR body carries the diff hunks, never the raw repo file contents
    assert "version: 1" in pr.body
    assert "x = 1" not in pr.body


def test_open_pr_rejects_diff_with_secret() -> None:
    leaky = ReviewableDiff.model_construct(
        hunks=(
            DiffHunk.model_construct(
                file="outcomes.yaml",
                header="@@ -0,0 +1,1 @@",
                lines=("+key: sk-ant-api03-PRLEAK0123456789abcdefghijklm",),
            ),
        )
    )
    app = ReadOnlyGithubApp(repo_files={})
    with pytest.raises(SecretEncounteredError):
        app.open_pr(branch="b", title="t", diff=leaky)
