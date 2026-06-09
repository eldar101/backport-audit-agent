from backport_audit.audit import build_summary, count_closed_issues, is_closed_issue
from backport_audit.models import AuditStatus, IssueAuditResult, JiraIssue, VerificationResult


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


def test_build_summary_uses_requested_audit_buckets():
    results = [
        audit_result("PROJ-1", "Closed", AuditStatus.BACKPORTED_CONFIRMED),
        audit_result("PROJ-2", "Closed", AuditStatus.PROBABLY_BACKPORTED),
        audit_result("PROJ-3", "Closed", AuditStatus.NOT_BACKPORTED),
        audit_result("PROJ-4", "Closed", AuditStatus.PR_NOT_MERGED),
        audit_result("PROJ-5", "Closed", AuditStatus.CLOSED_NO_PR),
        audit_result("PROJ-6", "Closed", AuditStatus.MANUAL_REVIEW),
        audit_result("PROJ-7", "Open", AuditStatus.OPEN_OR_UNRESOLVED),
    ]

    summary = build_summary("1.2.0-rc1", "release-1.2", results, "Closed")

    assert summary.closed_bugs == 6
    assert summary.not_closed_bugs == 1
    assert summary.closed_with_pr_backported == 2
    assert summary.closed_with_pr_not_backported == 2
    assert summary.closed_without_pr == 1
    assert summary.closed_with_pr_needs_review == 1


def audit_result(issue_key: str, issue_status: str, audit_status: AuditStatus) -> IssueAuditResult:
    return IssueAuditResult(
        issue=JiraIssue(
            key=issue_key,
            summary="Fix bug",
            status=issue_status,
            resolution=None,
        ),
        pull_requests=[],
        verification=VerificationResult(status=audit_status, method="test"),
    )
