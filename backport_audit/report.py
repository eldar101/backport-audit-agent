from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path

from rich.console import Console
from rich.table import Table

from backport_audit.models import AuditStatus, AuditSummary, IssueAuditResult

BUCKET_CLOSED = "bugs that are closed"
BUCKET_NOT_CLOSED = "bugs that are not closed"
BUCKET_BACKPORTED = "bugs that are closed, have PR, and are backported"
BUCKET_NOT_BACKPORTED = "bugs that are closed, have PR, and are not backported"
BUCKET_NO_PR = "bugs that are closed and do not have PR"


def print_summary(console: Console, summary: AuditSummary, results: list[IssueAuditResult]) -> None:
    console.print()
    console.print(f"[bold]FixVersion:[/bold] {summary.fix_version}")
    console.print(f"[bold]Target branch:[/bold] {summary.target_branch}")

    table = Table(title="Backport Audit Summary")
    table.add_column("Bucket")
    table.add_column("Count", justify="right")
    for label, value in summary_rows(summary):
        table.add_row(label, str(value))
    console.print(table)

    detail = Table(title="Issue Results")
    detail.add_column("Bucket")
    detail.add_column("Issue")
    detail.add_column("Status")
    detail.add_column("PRs")
    for result in results:
        detail.add_row(
            bucket_for_result(result, summary.closed_status),
            result.issue.key,
            result.issue.status,
            ", ".join(pr.ref.url for pr in result.pull_requests) or "-",
        )
    console.print(detail)


def write_reports(
    *,
    output_dir: Path,
    summary: AuditSummary,
    results: list[IssueAuditResult],
    jira_url: str,
) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_version = summary.fix_version.replace("/", "_")
    markdown_path = output_dir / f"backport-audit-{safe_version}.md"
    json_path = output_dir / f"backport-audit-{safe_version}.json"
    csv_path = output_dir / f"backport-audit-{safe_version}.csv"

    grouped = grouped_results(results, summary.closed_status)
    markdown_path.write_text(render_markdown(summary, grouped, jira_url), encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {
                "summary": asdict(summary),
                "buckets": {
                    bucket: [result_to_dict(result, jira_url) for result in bucket_results]
                    for bucket, bucket_results in grouped.items()
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    write_csv(csv_path, grouped, jira_url)
    return markdown_path, json_path, csv_path


def summary_rows(summary: AuditSummary) -> list[tuple[str, int]]:
    return [
        ("total bugs", summary.total_bugs),
        (BUCKET_CLOSED, summary.closed_bugs),
        (BUCKET_NOT_CLOSED, summary.not_closed_bugs),
        (BUCKET_BACKPORTED, summary.closed_with_pr_backported),
        (BUCKET_NOT_BACKPORTED, summary.closed_with_pr_not_backported),
        (BUCKET_NO_PR, summary.closed_without_pr),
    ]


def render_markdown(
    summary: AuditSummary,
    grouped: dict[str, list[IssueAuditResult]],
    jira_url: str,
) -> str:
    lines = [
        f"# Backport Audit: {summary.fix_version}",
        "",
        f"- Target branch: `{summary.target_branch}`",
    ]
    lines.extend(f"- {label}: {value}" for label, value in summary_rows(summary))
    lines.append("")

    for bucket, bucket_results in grouped.items():
        lines.extend(
            [
                f"## {bucket} ({len(bucket_results)})",
                "",
                "| Issue | Status | PRs | Result | Evidence |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for result in bucket_results:
            issue = f"[{result.issue.key}]({issue_url(jira_url, result.issue.key)})"
            prs = "<br>".join(f"[#{pr.ref.number}]({pr.ref.url})" for pr in result.pull_requests)
            lines.append(
                "| "
                + " | ".join(
                    [
                        issue,
                        _escape(result.issue.status),
                        prs or "-",
                        result.verification.status.value,
                        _escape(short_evidence(result)),
                    ]
                )
                + " |"
            )
        lines.append("")
    return "\n".join(lines)


def write_csv(
    path: Path,
    grouped: dict[str, list[IssueAuditResult]],
    jira_url: str,
) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "bucket",
                "issue",
                "issue_url",
                "summary",
                "jira_status",
                "result",
                "pr_links",
                "evidence",
            ],
        )
        writer.writeheader()
        for bucket, bucket_results in grouped.items():
            for result in bucket_results:
                writer.writerow(result_to_dict(result, jira_url, bucket=bucket))


def grouped_results(
    results: list[IssueAuditResult],
    closed_status: str,
) -> dict[str, list[IssueAuditResult]]:
    grouped = {
        BUCKET_CLOSED: [],
        BUCKET_NOT_CLOSED: [],
        BUCKET_BACKPORTED: [],
        BUCKET_NOT_BACKPORTED: [],
        BUCKET_NO_PR: [],
    }
    for result in results:
        bucket = bucket_for_result(result, closed_status)
        if bucket == BUCKET_CLOSED:
            continue
        grouped[bucket].append(result)
        if bucket != BUCKET_NOT_CLOSED:
            grouped[BUCKET_CLOSED].append(result)
    return grouped


def bucket_for_result(result: IssueAuditResult, closed_status: str) -> str:
    if result.issue.status.strip().lower() != closed_status.strip().lower():
        return BUCKET_NOT_CLOSED
    if result.verification.status == AuditStatus.CLOSED_NO_PR:
        return BUCKET_NO_PR
    if result.verification.status in {
        AuditStatus.BACKPORTED_CONFIRMED,
        AuditStatus.PROBABLY_BACKPORTED,
    }:
        return BUCKET_BACKPORTED
    return BUCKET_NOT_BACKPORTED


def result_to_dict(
    result: IssueAuditResult,
    jira_url: str,
    *,
    bucket: str | None = None,
) -> dict[str, str]:
    return {
        "bucket": bucket or "",
        "issue": result.issue.key,
        "issue_url": issue_url(jira_url, result.issue.key),
        "summary": result.issue.summary,
        "jira_status": result.issue.status,
        "result": result.verification.status.value,
        "pr_links": " ".join(pr.ref.url for pr in result.pull_requests),
        "evidence": short_evidence(result),
    }


def issue_url(jira_url: str, issue_key: str) -> str:
    return f"{jira_url.rstrip('/')}/browse/{issue_key}"


def short_evidence(result: IssueAuditResult) -> str:
    return " | ".join(result.verification.evidence) or result.verification.error or ""


def _escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
