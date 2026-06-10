from backport_audit.github_client import GitHubClient
from backport_audit.models import PullRequestRef


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.links = {}

    def json(self):
        return self._payload

    def raise_for_status(self) -> None:
        return None


class FakeSession:
    def __init__(self) -> None:
        self.headers = {}

    def get(self, url: str, params=None, headers=None):
        if url.endswith("/pulls/123"):
            return FakeResponse(
                {
                    "title": "PROJ-1 fix",
                    "body": "",
                    "user": {"login": "octocat"},
                    "state": "closed",
                    "merged": True,
                    "merge_commit_sha": "abc123",
                    "base": {"ref": "main"},
                }
            )
        if url.endswith("/pulls/123/commits"):
            return FakeResponse(
                [
                    {
                        "sha": "abc123",
                        "commit": {"message": "PROJ-1 fix"},
                    }
                ]
            )
        if url.endswith("/pulls/123/files"):
            return FakeResponse([{"filename": "main.go"}])
        raise AssertionError(f"Unexpected URL: {url}")


def test_get_pr_includes_creator_login():
    client = GitHubClient("token")
    client.session = FakeSession()

    details = client.get_pr(
        PullRequestRef(
            repo="owner/repo",
            number=123,
            url="https://github.com/owner/repo/pull/123",
        )
    )

    assert details.author == "octocat"
