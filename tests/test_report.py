from backport_audit.models import (
    AuditStatus,
    AuditSummary,
    IssueAuditResult,
    JiraIssue,
    PullRequestDetails,
    PullRequestRef,
    VerificationResult,
)
from backport_audit.report import (
    BUCKET_BACKPORTED,
    BUCKET_CLOSED,
    BUCKET_NO_PR,
    BUCKET_NOT_BACKPORTED,
    BUCKET_NOT_CLOSED,
    csv_safe,
    grouped_results,
    render_markdown,
    write_reports,
)


def test_grouped_results_use_requested_buckets():
    results = [
        audit_result("PROJ-1", "Closed", AuditStatus.BACKPORTED_CONFIRMED, with_pr=True),
        audit_result("PROJ-2", "Closed", AuditStatus.NOT_BACKPORTED, with_pr=True),
        audit_result("PROJ-3", "Closed", AuditStatus.CLOSED_NO_PR),
        audit_result("PROJ-4", "Open", AuditStatus.OPEN_OR_UNRESOLVED),
    ]

    grouped = grouped_results(results, "Closed")

    assert [result.issue.key for result in grouped[BUCKET_CLOSED]] == [
        "PROJ-1",
        "PROJ-2",
        "PROJ-3",
    ]
    assert [result.issue.key for result in grouped[BUCKET_BACKPORTED]] == ["PROJ-1"]
    assert [result.issue.key for result in grouped[BUCKET_NOT_BACKPORTED]] == ["PROJ-2"]
    assert [result.issue.key for result in grouped[BUCKET_NO_PR]] == ["PROJ-3"]
    assert [result.issue.key for result in grouped[BUCKET_NOT_CLOSED]] == ["PROJ-4"]


def test_markdown_report_includes_issue_and_pr_links():
    results = [
        audit_result("PROJ-1", "Closed", AuditStatus.BACKPORTED_CONFIRMED, with_pr=True),
    ]
    summary = AuditSummary(
        fix_version="1.2.0-rc1",
        target_branch="release-1.2",
        closed_status="Closed",
        total_bugs=1,
        closed_bugs=1,
        not_closed_bugs=0,
        closed_with_pr_backported=1,
        closed_with_pr_not_backported=0,
        closed_without_pr=0,
    )

    markdown = render_markdown(
        summary,
        grouped_results(results, "Closed"),
        "https://jira.example.com",
    )

    assert "[PROJ-1](https://jira.example.com/browse/PROJ-1)" in markdown
    assert "[#123](https://github.com/owner/repo/pull/123)" in markdown
    assert "release-blocker, qe" in markdown
    assert BUCKET_BACKPORTED in markdown


def test_csv_safe_neutralizes_spreadsheet_formulas():
    assert csv_safe("=cmd|'/C calc'!A0") == "'=cmd|'/C calc'!A0"
    assert csv_safe("+SUM(1,1)") == "'+SUM(1,1)"
    assert csv_safe("@HYPERLINK(\"https://example.com\")") == "'@HYPERLINK(\"https://example.com\")"
    assert csv_safe("normal text") == "normal text"


def test_write_reports_defaults_to_markdown_and_csv(tmp_path):
    paths = write_reports(
        output_dir=tmp_path,
        summary=summary(),
        results=[audit_result("PROJ-1", "Closed", AuditStatus.BACKPORTED_CONFIRMED)],
        jira_url="https://jira.example.com",
    )

    assert [path.suffix for path in paths] == [".md", ".csv"]
    assert (tmp_path / "backport-audit-1.2.0-rc1.md").exists()
    assert (tmp_path / "backport-audit-1.2.0-rc1.csv").exists()
    assert not (tmp_path / "backport-audit-1.2.0-rc1.json").exists()
    assert "release-blocker, qe" in (tmp_path / "backport-audit-1.2.0-rc1.csv").read_text()


def test_write_reports_can_include_json(tmp_path):
    paths = write_reports(
        output_dir=tmp_path,
        summary=summary(),
        results=[audit_result("PROJ-1", "Closed", AuditStatus.BACKPORTED_CONFIRMED)],
        jira_url="https://jira.example.com",
        include_json=True,
    )

    assert [path.suffix for path in paths] == [".md", ".csv", ".json"]
    assert (tmp_path / "backport-audit-1.2.0-rc1.json").exists()


def summary() -> AuditSummary:
    return AuditSummary(
        fix_version="1.2.0-rc1",
        target_branch="release-1.2",
        closed_status="Closed",
        total_bugs=1,
        closed_bugs=1,
        not_closed_bugs=0,
        closed_with_pr_backported=1,
        closed_with_pr_not_backported=0,
        closed_without_pr=0,
    )


def audit_result(
    issue_key: str,
    issue_status: str,
    audit_status: AuditStatus,
    *,
    with_pr: bool = False,
) -> IssueAuditResult:
    return IssueAuditResult(
        issue=JiraIssue(
            key=issue_key,
            summary="Fix bug",
            status=issue_status,
            resolution=None,
            labels=["release-blocker", "qe"],
        ),
        pull_requests=[pull_request()] if with_pr else [],
        verification=VerificationResult(
            status=audit_status,
            method="test",
            evidence=["test evidence"],
        ),
    )


def pull_request() -> PullRequestDetails:
    return PullRequestDetails(
        ref=PullRequestRef(
            repo="owner/repo",
            number=123,
            url="https://github.com/owner/repo/pull/123",
        ),
        title="PROJ-1 fix bug",
        body="",
        state="closed",
        merged=True,
        merge_commit_sha="abc123",
        base_branch="main",
    )
