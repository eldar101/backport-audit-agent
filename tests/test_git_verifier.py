from pathlib import Path

import pytest

from backport_audit.git_verifier import GitVerifier


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
