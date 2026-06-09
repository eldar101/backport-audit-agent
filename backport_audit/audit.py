from __future__ import annotations

from collections import Counter

from rich.console import Console

from backport_audit.git_verifier import GitVerifier
from backport_audit.github_client import GitHubClient
from backport_audit.jira_client import JiraClient
from backport_audit.models import (
    AuditStatus,
    AuditSummary,
    IssueAuditResult,
    VerificationResult,
)
from backport_audit.pr_discovery import discover_pull_requests


def run_audit(
    *,
    jira: JiraClient,
    github: GitHubClient,
    verifier: GitVerifier,
    fix_version: str,
    target_branch: str,
    jira_project: str | None,
    github_repo: str,
    console: Console,
) -> tuple[AuditSummary, list[IssueAuditResult]]:
    issues = jira.search_bugs(fix_version, jira_project)
    verifier.ensure_repo()

    results: list[IssueAuditResult] = []
    for issue in issues:
        console.print(f"[cyan]Auditing {issue.key}[/cyan] {issue.summary}")
        pr_refs = discover_pull_requests(issue, github=github, default_repo=github_repo)
        pr_details = []
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

        if not issue.is_closed:
            status_evidence = (
                f"Jira status is {issue.status}; resolution is {issue.resolution or '-'}"
            )
            verification = VerificationResult(
                status=AuditStatus.OPEN_OR_UNRESOLVED,
                method="jira_status",
                evidence=[status_evidence],
            )
        elif not pr_details:
            verification = VerificationResult(
                status=AuditStatus.CLOSED_NO_PR,
                method="pr_discovery",
                evidence=["Closed Jira bug has no discovered GitHub PR link"],
            )
        else:
            verification = _best_pr_verification(
                issue_key=issue.key,
                prs=pr_details,
                verifier=verifier,
                target_branch=target_branch,
            )

        results.append(
            IssueAuditResult(
                issue=issue,
                pull_requests=pr_details,
                verification=verification,
            )
        )

    return build_summary(fix_version, target_branch, results), results


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
) -> AuditSummary:
    counts = Counter(result.verification.status for result in results)
    closed = [result for result in results if result.issue.is_closed]
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
