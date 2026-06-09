from backport_audit.audit import is_closed_issue
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
