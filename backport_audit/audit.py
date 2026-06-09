from __future__ import annotations

from collections import Counter

from rich.console import Console

from backport_audit.git_verifier import GitVerifier
from backport_audit.github_client import GitHubClient
from backport_audit.jira_client import JiraClient, add_status_filter
from backport_audit.models import (
    AuditStatus,
    AuditSummary,
    IssueAuditResult,
    VerificationResult,
)
from backport_audit.pr_discovery import discover_pull_requests
from backport_audit.repo_routing import RepoRoute, select_repo_for_issue


def run_audit(
    *,
    jira: JiraClient,
    github: GitHubClient,
    fix_version: str,
    target_branch: str,
    jira_project: str | None,
    issue_type: str | None,
    jql_override: str | None,
    closed_status: str,
    github_repo: str,
    repo_routes: list[RepoRoute],
    verifiers: dict[str, GitVerifier],
    console: Console,
) -> tuple[AuditSummary, list[IssueAuditResult]]:
    jql = jql_override or jira.build_jql(
        fix_version=fix_version,
        project=jira_project,
        issue_type=issue_type,
    )
    closed_jql = add_status_filter(jql, closed_status)
    console.print(f"[bold]Jira JQL:[/bold] {jql}")
    console.print(f"[bold]Closed Jira JQL:[/bold] {closed_jql}")
    total_count = jira.count_issues(jql)
    closed_count = jira.count_issues(closed_jql)
    console.print(f"[bold]Jira total count:[/bold] {total_count}")
    console.print(f"[bold]Jira closed count:[/bold] {closed_count}")
    console.print("[cyan]Fetching Jira issue details...[/cyan]")
    issues = jira.search_bugs(
        fix_version,
        jira_project,
        issue_type=issue_type,
        jql_override=jql_override,
    )
    console.print(f"[bold]Closed status:[/bold] {closed_status}")
    if total_count > 0 and not issues:
        raise RuntimeError(
            f"Jira count API returned {total_count} issues for '{jql}', but search returned 0. "
            "This indicates a Jira search pagination or response parsing bug in the tool."
        )
    if not issues:
        console.print(
            "[yellow]Jira returned 0 issues. Use --jql with the exact query that works in Jira "
            "if this is unexpected.[/yellow]"
        )
        return build_summary(fix_version, target_branch, [], closed_status), []
    console.print(f"[green]Fetched {len(issues)} Jira issues.[/green]")

    results: list[IssueAuditResult] = []
    closed_total = count_closed_issues(issues, closed_status)
    closed_index = 0
    for issue in issues:
        pr_details = []
        if not is_closed_issue(issue, closed_status):
            console.print(f"[cyan]Skipping open {issue.key}[/cyan] {issue.summary}")
            status_evidence = (
                f"Jira status is {issue.status}; resolution is {issue.resolution or '-'}"
            )
            verification = VerificationResult(
                status=AuditStatus.OPEN_OR_UNRESOLVED,
                method="jira_status",
                evidence=[status_evidence],
            )
        else:
            closed_index += 1
            issue_repo = select_repo_for_issue(issue, github_repo, repo_routes)
            console.print(
                f"[cyan]Auditing {closed_index}/{closed_total} {issue.key}[/cyan] "
                f"[{issue_repo}] {issue.summary}"
            )
            issue_verifier = verifiers[issue_repo]
            issue_verifier.ensure_repo()
            pr_refs = discover_pull_requests(
                issue,
                jira=jira,
                github=github,
                default_repo=issue_repo,
            )
            for ref in pr_refs:
                try:
                    pr_details.append(github.get_pr(ref))
                except Exception as exc:  # noqa: BLE001
                    results.append(
                        IssueAuditResult(
                            issue=issue,
                            pull_requests=[],
                            verification=VerificationResult(
                                status=AuditStatus.ERROR,
                                method="github_pr_lookup",
                                error=str(exc),
                                evidence=[f"Failed to fetch {ref.url}"],
                            ),
                        )
                    )

            if not pr_details:
                verification = VerificationResult(
                    status=AuditStatus.CLOSED_NO_PR,
                    method="pr_discovery",
                    evidence=["Closed Jira bug has no discovered GitHub PR link"],
                )
            else:
                verification = _best_pr_verification(
                    issue_key=issue.key,
                    prs=pr_details,
                    verifier=issue_verifier,
                    target_branch=target_branch,
                )

        results.append(
            IssueAuditResult(
                issue=issue,
                pull_requests=pr_details,
                verification=verification,
            )
        )

    return build_summary(fix_version, target_branch, results, closed_status), results


def _best_pr_verification(
    *,
    issue_key: str,
    prs,
    verifier: GitVerifier,
    target_branch: str,
) -> VerificationResult:
    priority = {
        AuditStatus.BACKPORTED_CONFIRMED: 0,
        AuditStatus.PROBABLY_BACKPORTED: 1,
        AuditStatus.MANUAL_REVIEW: 2,
        AuditStatus.PR_NOT_MERGED: 3,
        AuditStatus.NOT_BACKPORTED: 4,
        AuditStatus.ERROR: 5,
    }
    results: list[VerificationResult] = []
    for pr in prs:
        try:
            results.append(
                verifier.verify_pr(
                    issue_key=issue_key,
                    pr=pr,
                    target_branch=target_branch,
                )
            )
        except Exception as exc:  # noqa: BLE001
            results.append(
                VerificationResult(
                    status=AuditStatus.ERROR,
                    method="git_verification",
                    error=str(exc),
                    evidence=[f"Failed to verify {pr.ref.url}"],
                )
            )
    return sorted(results, key=lambda result: priority.get(result.status, 99))[0]


def build_summary(
    fix_version: str,
    target_branch: str,
    results: list[IssueAuditResult],
    closed_status: str = "Closed",
) -> AuditSummary:
    counts = Counter(result.verification.status for result in results)
    closed = [result for result in results if is_closed_issue(result.issue, closed_status)]
    closed_with_pr = [result for result in closed if result.pull_requests]
    return AuditSummary(
        fix_version=fix_version,
        target_branch=target_branch,
        total_bugs=len(results),
        closed_bugs=len(closed),
        open_or_unresolved=counts[AuditStatus.OPEN_OR_UNRESOLVED],
        closed_with_pr=len(closed_with_pr),
        closed_without_pr=counts[AuditStatus.CLOSED_NO_PR],
        backported_confirmed=counts[AuditStatus.BACKPORTED_CONFIRMED],
        probably_backported=counts[AuditStatus.PROBABLY_BACKPORTED],
        not_backported=counts[AuditStatus.NOT_BACKPORTED],
        manual_review=counts[AuditStatus.MANUAL_REVIEW],
        pr_not_merged=counts[AuditStatus.PR_NOT_MERGED],
        errors=counts[AuditStatus.ERROR],
    )


def is_closed_issue(issue, closed_status: str) -> bool:
    return issue.status.strip().lower() == closed_status.strip().lower()


def count_closed_issues(issues, closed_status: str) -> int:
    return sum(1 for issue in issues if is_closed_issue(issue, closed_status))
