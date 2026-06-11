from backport_audit.config import derive_target_branch
from backport_audit.models import JiraIssue, PullRequestRef
from backport_audit.pr_discovery import discover_pull_requests, extract_pr_refs


def test_derive_target_branch_from_rc_fix_version():
    assert derive_target_branch("1.2.0-rc1") == "release-1.2"


def test_extract_pr_refs_from_github_urls():
    refs = extract_pr_refs("Fixed by https://github.com/example/service/pull/3012")

    assert len(refs) == 1
    assert refs[0].repo == "example/service"
    assert refs[0].number == 3012


class FakeGitHub:
    def __init__(self) -> None:
        self.search_calls = 0

    def search_prs(self, repo: str, query: str, base_branch: str | None = None):
        self.search_calls += 1
        return [PullRequestRef(repo=repo, number=7, url=f"https://github.com/{repo}/pull/7")]


def test_discover_pull_requests_searches_github_even_when_jira_has_pr_link():
    github = FakeGitHub()
    issue = JiraIssue(
        key="PROJ-1",
        summary="Fix bug",
        status="Closed",
        resolution="Done",
        remote_links=["https://github.com/example/service/pull/3012"],
    )

    refs = discover_pull_requests(issue, github=github, default_repo="example/service")

    assert [ref.number for ref in refs] == [7, 3012]
    assert github.search_calls == 1


def test_discover_pull_requests_searches_github_when_jira_has_no_pr_link():
    github = FakeGitHub()
    issue = JiraIssue(key="PROJ-1", summary="Fix bug", status="Closed", resolution="Done")

    refs = discover_pull_requests(issue, github=github, default_repo="example/service")

    assert [ref.number for ref in refs] == [7]
    assert github.search_calls == 1
