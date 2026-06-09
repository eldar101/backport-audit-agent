from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path

from rich.console import Console
from rich.table import Table

from backport_audit.models import AuditSummary, IssueAuditResult


def print_summary(console: Console, summary: AuditSummary, results: list[IssueAuditResult]) -> None:
    console.print()
    console.print(f"[bold]FixVersion:[/bold] {summary.fix_version}")
    console.print(f"[bold]Target branch:[/bold] {summary.target_branch}")

    table = Table(title="Backport Audit Summary")
    table.add_column("Metric")
    table.add_column("Count", justify="right")
    for label, value in [
        ("Total bugs", summary.total_bugs),
        ("Bugs that are closed", summary.closed_bugs),
        ("Bugs that are not closed", summary.not_closed_bugs),
        ("Closed, have PR, backported", summary.closed_with_pr_backported),
        ("Closed, have PR, not backported", summary.closed_with_pr_not_backported),
        ("Closed, do not have PR", summary.closed_without_pr),
        ("Closed, have PR, needs review", summary.closed_with_pr_needs_review),
        ("Errors", summary.errors),
    ]:
        table.add_row(label, str(value))
    console.print(table)

    detail = Table(title="Issue Results")
    detail.add_column("Issue")
    detail.add_column("Status")
    detail.add_column("PRs")
    detail.add_column("Method")
    detail.add_column("Evidence")
    for result in results:
        prs = ", ".join(pr.ref.url for pr in result.pull_requests) or "-"
        evidence = "; ".join(result.verification.evidence[:2]) or result.verification.error or "-"
        detail.add_row(
            result.issue.key,
            result.verification.status.value,
            prs,
            result.verification.method,
            evidence,
        )
    console.print(detail)


def write_reports(
    *,
    output_dir: Path,
    summary: AuditSummary,
    results: list[IssueAuditResult],
) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_version = summary.fix_version.replace("/", "_")
    markdown_path = output_dir / f"backport-audit-{safe_version}.md"
    json_path = output_dir / f"backport-audit-{safe_version}.json"
    csv_path = output_dir / f"backport-audit-{safe_version}.csv"

    markdown_path.write_text(render_markdown(summary, results), encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {
                "summary": asdict(summary),
                "results": [asdict(result) for result in results],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    write_csv(csv_path, results)
    return markdown_path, json_path, csv_path


def render_markdown(summary: AuditSummary, results: list[IssueAuditResult]) -> str:
    lines = [
        f"# Backport Audit: {summary.fix_version}",
        "",
        f"- Target branch: `{summary.target_branch}`",
        f"- Total bugs: {summary.total_bugs}",
        f"- Bugs that are closed: {summary.closed_bugs}",
        f"- Bugs that are not closed: {summary.not_closed_bugs}",
        f"- Closed, have PR, backported: {summary.closed_with_pr_backported}",
        f"- Closed, have PR, not backported: {summary.closed_with_pr_not_backported}",
        f"- Closed, do not have PR: {summary.closed_without_pr}",
        f"- Closed, have PR, needs review: {summary.closed_with_pr_needs_review}",
        f"- Errors: {summary.errors}",
        "",
        "## Results",
        "",
        "| Issue | Jira status | Resolution | Result | PRs | Method | Evidence |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for result in results:
        prs = "<br>".join(pr.ref.url for pr in result.pull_requests) or "-"
        evidence = "<br>".join(result.verification.evidence) or result.verification.error or "-"
        lines.append(
            "| "
            + " | ".join(
                [
                    result.issue.key,
                    _escape(result.issue.status),
                    _escape(result.issue.resolution or "-"),
                    result.verification.status.value,
                    prs,
                    _escape(result.verification.method),
                    _escape(evidence),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_csv(path: Path, results: list[IssueAuditResult]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "issue",
                "summary",
                "jira_status",
                "resolution",
                "result",
                "prs",
                "method",
                "evidence",
                "error",
            ],
        )
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "issue": result.issue.key,
                    "summary": result.issue.summary,
                    "jira_status": result.issue.status,
                    "resolution": result.issue.resolution or "",
                    "result": result.verification.status.value,
                    "prs": " ".join(pr.ref.url for pr in result.pull_requests),
                    "method": result.verification.method,
                    "evidence": " | ".join(result.verification.evidence),
                    "error": result.verification.error or "",
                }
            )


def _escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
