from __future__ import annotations

from collections.abc import Iterable

from backport_audit.github_client import GitHubClient
from backport_audit.models import JiraIssue, PullRequestRef
from backport_audit.util import GITHUB_PR_RE, normalize_repo


def discover_pull_requests(
    issue: JiraIssue,
    *,
    github: GitHubClient,
    default_repo: str,
) -> list[PullRequestRef]:
    refs: dict[tuple[str, int], PullRequestRef] = {}
    for text in _issue_text_sources(issue):
        for ref in extract_pr_refs(text):
            refs[(ref.repo, ref.number)] = ref

    for ref in github.search_prs(default_repo, issue.key):
        refs[(ref.repo, ref.number)] = ref

    return sorted(refs.values(), key=lambda ref: (ref.repo, ref.number))


def extract_pr_refs(text: str) -> list[PullRequestRef]:
    refs: list[PullRequestRef] = []
    for match in GITHUB_PR_RE.finditer(text or ""):
        repo = normalize_repo(match.group("owner"), match.group("repo"))
        number = int(match.group("number"))
        refs.append(PullRequestRef(repo=repo, number=number, url=match.group(0)))
    return refs


def _issue_text_sources(issue: JiraIssue) -> Iterable[str]:
    yield issue.description
    yield from issue.comments
    yield from issue.remote_links
