from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from backport_audit.audit import run_audit
from backport_audit.config import derive_target_branch, prompt_missing_auth
from backport_audit.git_verifier import GitVerifier
from backport_audit.github_client import GitHubClient
from backport_audit.jira_client import JiraClient
from backport_audit.report import print_summary, write_reports

app = typer.Typer(help="Audit Jira bugs for release branch backport coverage.")
console = Console()


@app.command("version")
def version() -> None:
    from backport_audit import __version__

    console.print(__version__)


@app.command("audit")
def audit(
    fix_version: Annotated[str, typer.Option("--fix-version", prompt=True)],
    repo: Annotated[str, typer.Option("--repo", help="GitHub repo in owner/name form.")],
    jira_url: Annotated[
        str | None,
        typer.Option("--jira-url", envvar="JIRA_BASE_URL", help="Jira base URL."),
    ] = None,
    project: Annotated[
        str | None,
        typer.Option("--project", help="Optional Jira project key, for example EDM."),
    ] = None,
    target_branch: Annotated[
        str | None,
        typer.Option("--target-branch", help="Target branch. Defaults to release-MAJOR.MINOR."),
    ] = None,
    clone_dir: Annotated[
        Path | None,
        typer.Option("--clone-dir", help="Local clone used for git verification."),
    ] = None,
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", help="Directory for Markdown, JSON, and CSV reports."),
    ] = Path("reports"),
) -> None:
    if not jira_url:
        jira_url = console.input("Jira base URL: ").strip()
    if not jira_url:
        raise typer.BadParameter("Jira base URL is required.")

    target_branch = target_branch or derive_target_branch(fix_version)
    clone_dir = clone_dir or Path(".cache") / repo.replace("/", "-")

    jira_user, jira_token, github_token = prompt_missing_auth(
        jira_base_url=jira_url,
        jira_user=os.getenv("JIRA_USER") or os.getenv("JIRA_EMAIL"),
        jira_token=os.getenv("JIRA_TOKEN"),
        github_token=os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN"),
        console=console,
    )

    jira = JiraClient(jira_url, jira_user, jira_token)
    github = GitHubClient(github_token)
    verifier = GitVerifier(clone_dir, repo)

    summary, results = run_audit(
        jira=jira,
        github=github,
        verifier=verifier,
        fix_version=fix_version,
        target_branch=target_branch,
        jira_project=project,
        github_repo=repo,
        console=console,
    )
    print_summary(console, summary, results)
    markdown_path, json_path, csv_path = write_reports(
        output_dir=output_dir,
        summary=summary,
        results=results,
    )
    console.print()
    console.print("[green]Reports written:[/green]")
    console.print(f"- {markdown_path}")
    console.print(f"- {json_path}")
    console.print(f"- {csv_path}")


if __name__ == "__main__":
    app()
