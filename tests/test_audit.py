from backport_audit.audit import count_closed_issues, is_closed_issue
from backport_audit.models import JiraIssue


def test_is_closed_issue_uses_configured_status():
    issue = JiraIssue(
        key="PROJ-1",
        summary="Fix bug",
        status="Closed",
        resolution=None,
    )

    assert is_closed_issue(issue, "Closed")
    assert not is_closed_issue(issue, "Done")


def test_count_closed_issues_uses_configured_status():
    issues = [
        JiraIssue(key="PROJ-1", summary="Fix bug", status="Closed", resolution=None),
        JiraIssue(key="PROJ-2", summary="Open bug", status="Open", resolution=None),
        JiraIssue(key="PROJ-3", summary="Another bug", status="Closed", resolution=None),
    ]

    assert count_closed_issues(issues, "Closed") == 2
