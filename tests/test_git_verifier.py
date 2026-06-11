from pathlib import Path

import pytest

from backport_audit.git_verifier import GitVerifier
from backport_audit.models import AuditStatus, PullRequestDetails, PullRequestRef


def test_git_verifier_resolves_relative_clone_dir():
    verifier = GitVerifier(Path(".cache") / "owner-repo", "owner/repo")

    assert verifier.repo_dir.is_absolute()


def test_git_verifier_rejects_non_git_non_empty_cache(tmp_path: Path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / "partial").write_text("not a clone", encoding="utf-8")
    verifier = GitVerifier(repo_dir, "owner/repo")

    with pytest.raises(RuntimeError, match="exists but is not a git repository"):
        verifier.ensure_repo()


def test_git_verifier_can_confirm_unmerged_pr_by_patch_id(tmp_path: Path):
    verifier = PatchMatchVerifier(tmp_path / "repo", "owner/repo")
    pr = PullRequestDetails(
        ref=PullRequestRef(repo="owner/repo", number=12, url="https://github.com/owner/repo/pull/12"),
        title="NO-ISSUE: Backport fix",
        body="",
        state="closed",
        merged=False,
        merge_commit_sha=None,
        base_branch="main",
        commits=["abc123"],
    )

    result = verifier.verify_pr(
        issue_key="PROJ-1",
        pr=pr,
        target_branch="release-1.2",
    )

    assert result.status == AuditStatus.BACKPORTED_CONFIRMED
    assert result.method == "patch_id"
    assert verifier.fetched_pr_commits


class PatchMatchVerifier(GitVerifier):
    def __init__(self, repo_dir: Path, github_repo: str) -> None:
        super().__init__(repo_dir, github_repo)
        self.fetched_pr_commits = False

    def _resolve_target_ref(self, target_branch: str) -> str:
        return f"origin/{target_branch}"

    def _git_log_grep(self, pattern: str, target_ref: str) -> list[str]:
        return []

    def _ensure_pr_commits_available(self, pr: PullRequestDetails) -> None:
        self.fetched_pr_commits = True

    def _patch_id_match(self, source_commits: list[str], target_ref: str) -> str | None:
        return "Patch-id abc from source commit abc123 exists on origin/release-1.2 as def456"
