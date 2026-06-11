from __future__ import annotations

from rich.console import Console

from backport_audit.git_verifier import GitVerifier
from backport_audit.github_client import GitHubClient
from backport_audit.jira_client import JiraClient, add_status_filter
from backport_audit.models import (
    AuditStatus,
    AuditSummary,
    IssueAuditResult,
    JiraIssue,
    PullRequestDetails,
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
            seen_refs = {(ref.repo, ref.number) for ref in pr_refs}
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

            if repo_routes and _needs_routed_pr_search(issue.key, pr_details):
                routed_repos = list(dict.fromkeys(route.repo for route in repo_routes))
                for routed_repo in routed_repos:
                    if routed_repo == issue_repo:
                        continue
                    for ref in github.search_prs(routed_repo, issue.key):
                        if (ref.repo, ref.number) in seen_refs:
                            continue
                        seen_refs.add((ref.repo, ref.number))
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
                    verifiers=verifiers,
                    fallback_verifier=issue_verifier,
                    target_branch=target_branch,
                )
                if verification.status in {
                    AuditStatus.PR_NOT_MERGED,
                    AuditStatus.NOT_BACKPORTED,
                    AuditStatus.MANUAL_REVIEW,
                }:
                    verification = _prefer_routed_metadata_hit(
                        issue_key=issue.key,
                        verifiers=verifiers,
                        target_branch=target_branch,
                        fallback=verification,
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
    prs: list[PullRequestDetails],
    verifiers: dict[str, GitVerifier],
    fallback_verifier: GitVerifier,
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
            verifier = verifiers.get(pr.ref.repo, fallback_verifier)
            verifier.ensure_repo()
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


def _needs_routed_pr_search(issue_key: str, prs: list[PullRequestDetails]) -> bool:
    if not prs:
        return True
    normalized_issue = issue_key.lower()
    for pr in prs:
        haystack = "\n".join(
            [
                pr.title,
                pr.body,
                *pr.commit_subjects.values(),
            ]
        ).lower()
        if normalized_issue in haystack:
            return False
    return True


def _prefer_routed_metadata_hit(
    *,
    issue_key: str,
    verifiers: dict[str, GitVerifier],
    target_branch: str,
    fallback: VerificationResult,
) -> VerificationResult:
    hits: list[str] = []
    for repo, verifier in verifiers.items():
        try:
            verifier.ensure_repo()
            hits.extend(f"{repo}: {hit}" for hit in verifier.metadata_hits_for_issue(issue_key, target_branch))
        except Exception:
            continue
    if not hits:
        return fallback
    return VerificationResult(
        status=AuditStatus.PROBABLY_BACKPORTED,
        method="routed_branch_metadata_search",
        evidence=hits[:5],
    )


def build_summary(
    fix_version: str,
    target_branch: str,
    results: list[IssueAuditResult],
    closed_status: str = "Closed",
) -> AuditSummary:
    closed = [result for result in results if is_closed_issue(result.issue, closed_status)]
    return AuditSummary(
        fix_version=fix_version,
        target_branch=target_branch,
        closed_status=closed_status,
        total_bugs=len(results),
        closed_bugs=len(closed),
        not_closed_bugs=len(results) - len(closed),
        closed_with_pr_backported=count_statuses(
            closed,
            {AuditStatus.BACKPORTED_CONFIRMED, AuditStatus.PROBABLY_BACKPORTED},
        ),
        closed_with_pr_not_backported=count_statuses(
            closed,
            {
                AuditStatus.NOT_BACKPORTED,
                AuditStatus.PR_NOT_MERGED,
                AuditStatus.MANUAL_REVIEW,
                AuditStatus.ERROR,
            },
        ),
        closed_without_pr=count_statuses(closed, {AuditStatus.CLOSED_NO_PR}),
    )


def is_closed_issue(issue: JiraIssue, closed_status: str) -> bool:
    return issue.status.strip().lower() == closed_status.strip().lower()


def count_closed_issues(issues: list[JiraIssue], closed_status: str) -> int:
    return sum(1 for issue in issues if is_closed_issue(issue, closed_status))


def count_statuses(results: list[IssueAuditResult], statuses: set[AuditStatus]) -> int:
    return sum(1 for result in results if result.verification.status in statuses)
