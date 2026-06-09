from __future__ import annotations

import re
import subprocess
from pathlib import Path

GITHUB_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
GITHUB_PR_RE = re.compile(
    r"https://github\.com/(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+)/pull/(?P<number>\d+)"
)


def run_git(args: list[str], *, cwd: str | Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=False,
        text=True,
        capture_output=True,
    )


def normalize_repo(owner: str, repo: str) -> str:
    return f"{owner}/{repo}"


def validate_github_repo(value: str) -> str:
    repo = value.strip()
    if not GITHUB_REPO_RE.fullmatch(repo):
        raise ValueError("GitHub repository must use owner/repo format.")
    return repo
