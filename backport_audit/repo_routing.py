from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backport_audit.models import JiraIssue


@dataclass(frozen=True)
class RepoRoute:
    marker: str
    repo: str


def parse_repo_route(value: str) -> RepoRoute:
    marker, separator, repo = value.partition("=")
    if not separator or not marker.strip() or not repo.strip():
        raise ValueError("Repo route must use MARKER=owner/repo format.")
    if "/" not in repo:
        raise ValueError("Repo route repository must use owner/repo format.")
    return RepoRoute(marker=marker.strip(), repo=repo.strip())


def select_repo_for_issue(issue: JiraIssue, default_repo: str, routes: list[RepoRoute]) -> str:
    summary = issue.summary.lower()
    for route in routes:
        if route.marker.lower() in summary:
            return route.repo
    return default_repo


def default_clone_dir(base_clone_dir: Path | None, cache_root: Path, repo: str) -> Path:
    if base_clone_dir:
        if len(repo.split("/")) == 2:
            return base_clone_dir / repo.replace("/", "-")
        return base_clone_dir
    return cache_root / repo.replace("/", "-")
