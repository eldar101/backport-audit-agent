from __future__ import annotations

from backport_audit.jira_client import JiraClient, add_status_filter, build_jql, jira_text


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | list | None = None) -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.posts: list[tuple[str, dict]] = []
        self.gets: list[str] = []
        self.headers = {}
        self.auth = None

    def post(self, url: str, json: dict):
        self.posts.append((url, json))
        return self.responses.pop(0)

    def get(self, url: str):
        self.gets.append(url)
        return FakeResponse(200, [])


def test_search_bugs_uses_jira_cloud_enhanced_search():
    client = JiraClient("https://jira.example.com", "user@example.com", "token")
    client.session = FakeSession(
        [
            FakeResponse(
                200,
                {
                    "isLast": True,
                    "issues": [
                        {
                            "key": "PROJ-1",
                            "fields": {
                                "summary": "Fix bug",
                                "status": {"name": "Done"},
                                "resolution": {"name": "Done"},
                                "fixVersions": [{"name": "1.2.0-rc1"}],
                                "description": "",
                                "comment": {"comments": []},
                            },
                        }
                    ],
                },
            )
        ]
    )

    issues = client.search_bugs("1.2.0-rc1", "PROJ")

    assert issues[0].key == "PROJ-1"
    assert client.session.posts[0][0] == "https://jira.example.com/rest/api/3/search/jql"
    assert client.session.posts[0][1]["jql"] == (
        'project = PROJ AND fixVersion in ("1.2.0-rc1")'
    )
    assert client.session.gets == []


def test_search_bugs_falls_back_to_legacy_search_when_cloud_search_is_missing():
    client = JiraClient("https://jira.example.com", "user@example.com", "token")
    client.session = FakeSession(
        [
            FakeResponse(404),
            FakeResponse(200, {"total": 0, "issues": []}),
        ]
    )

    assert client.search_bugs("1.2.0-rc1", "PROJ") == []
    assert client.session.posts[0][0] == "https://jira.example.com/rest/api/3/search/jql"
    assert client.session.posts[1][0] == "https://jira.example.com/rest/api/2/search"


def test_jira_text_extracts_atlassian_document_format_text():
    assert jira_text(
        {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "hello"},
                        {"type": "text", "text": " world"},
                    ],
                }
            ],
        }
    ) == "hello\n world"


def test_build_jql_can_add_issue_type_filter():
    assert build_jql(fix_version="1.2.0-rc1", project="PROJ", issue_type="Bug") == (
        'project = PROJ AND fixVersion in ("1.2.0-rc1") AND issuetype = "Bug"'
    )


def test_build_jql_defaults_to_no_issue_type_filter():
    assert build_jql(fix_version="1.2.0-rc1", project="PROJ", issue_type=None) == (
        'project = PROJ AND fixVersion in ("1.2.0-rc1")'
    )


def test_search_bugs_accepts_exact_jql_override():
    client = JiraClient("https://jira.example.com", "user@example.com", "token")
    client.session = FakeSession([FakeResponse(200, {"isLast": True, "issues": []})])

    assert client.search_bugs("ignored", jql_override='project = PROJ AND labels = "foo"') == []
    assert client.session.posts[0][1]["jql"] == 'project = PROJ AND labels = "foo"'


def test_count_issues_uses_jira_cloud_count_endpoint():
    client = JiraClient("https://jira.example.com", "user@example.com", "token")
    client.session = FakeSession([FakeResponse(200, {"count": 42})])

    assert client.count_issues('fixVersion in ("1.2.0-rc1")') == 42
    assert client.session.posts[0][0] == (
        "https://jira.example.com/rest/api/3/search/approximate-count"
    )


def test_add_status_filter_preserves_order_by():
    assert add_status_filter(
        'fixVersion = "1.2.0-rc1" ORDER BY created DESC',
        "Closed",
    ) == 'fixVersion = "1.2.0-rc1" AND status = "Closed" ORDER BY created DESC'
