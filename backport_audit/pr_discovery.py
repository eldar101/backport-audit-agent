from __future__ import annotations

from collections.abc import Iterable

from backport_audit.github_client import GitHubClient
from backport_audit.jira_client import JiraClient
from backport_audit.models import JiraIssue, PullRequestRef
from backport_audit.util import GITHUB_PR_RE, normalize_repo


def discover_pull_requests(
    issue: JiraIssue,
    *,
    jira: JiraClient | None = None,
    github: GitHubClient,
    default_repo: str,
    search_repos: list[str] | None = None,
) -> list[PullRequestRef]:
    refs: dict[tuple[str, int], PullRequestRef] = {}
    if jira and not issue.remote_links:
        try:
            issue.remote_links.extend(jira.get_remote_links(issue.key))
        except Exception:
            pass

    for text in _issue_text_sources(issue):
        for ref in extract_pr_refs(text):
            refs[(ref.repo, ref.number)] = ref

    repos = list(dict.fromkeys([default_repo, *(search_repos or [])]))
    for repo in repos:
        for ref in github.search_prs(repo, issue.key):
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
