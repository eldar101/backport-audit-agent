from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from backport_audit.audit import run_audit
from backport_audit.config import (
    derive_target_branch,
    prompt_missing_auth,
    resolve_github_token,
    resolve_jira_base_url,
    resolve_jira_token,
    resolve_jira_user,
)
from backport_audit.git_verifier import GitVerifier
from backport_audit.github_client import GitHubClient
from backport_audit.jira_client import JiraClient
from backport_audit.repo_routing import default_clone_dir, parse_repo_route
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
    repo_route: Annotated[
        list[str] | None,
        typer.Option(
            "--repo-route",
            help="Route issues whose summary contains MARKER to another repo, MARKER=owner/repo.",
        ),
    ] = None,
    jira_url: Annotated[
        str | None,
        typer.Option("--jira-url", help="Jira base URL."),
    ] = None,
    project: Annotated[
        str | None,
        typer.Option("--project", help="Optional Jira project key, for example PROJ."),
    ] = None,
    issue_type: Annotated[
        str | None,
        typer.Option("--issue-type", help="Optional Jira issue type filter, for example Bug."),
    ] = None,
    closed_status: Annotated[
        str,
        typer.Option("--closed-status", help="Jira status treated as closed."),
    ] = "Closed",
    jql: Annotated[
        str | None,
        typer.Option("--jql", help="Exact JQL to use instead of generated fixVersion JQL."),
    ] = None,
    target_branch: Annotated[
        str | None,
        typer.Option("--target-branch", help="Target branch. Defaults to release-MAJOR.MINOR."),
    ] = None,
    clone_dir: Annotated[
        Path | None,
        typer.Option(
            "--clone-dir",
            help="Base clone directory. With routes, each repo gets a subdirectory.",
        ),
    ] = None,
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", help="Directory for Markdown, JSON, and CSV reports."),
    ] = Path("reports"),
) -> None:
    jira_url = resolve_jira_base_url(jira_url)
    if not jira_url:
        jira_url = console.input("Jira base URL: ").strip()
    if not jira_url:
        raise typer.BadParameter("Jira base URL is required.")

    target_branch = target_branch or derive_target_branch(fix_version)
    routes = [parse_repo_route(value) for value in repo_route or []]
    repos = {repo, *(route.repo for route in routes)}
    cache_root = Path(".cache")
    verifiers = {
        routed_repo: GitVerifier(
            default_clone_dir(clone_dir, cache_root, routed_repo),
            routed_repo,
        )
        for routed_repo in repos
    }

    jira_user, jira_token, github_token = prompt_missing_auth(
        jira_base_url=jira_url,
        jira_user=resolve_jira_user(jira_base_url=jira_url),
        jira_token=resolve_jira_token(jira_base_url=jira_url),
        github_token=resolve_github_token(),
        console=console,
    )

    jira = JiraClient(jira_url, jira_user, jira_token)
    github = GitHubClient(github_token)

    summary, results = run_audit(
        jira=jira,
        github=github,
        fix_version=fix_version,
        target_branch=target_branch,
        jira_project=project,
        issue_type=issue_type,
        jql_override=jql,
        closed_status=closed_status,
        github_repo=repo,
        repo_routes=routes,
        verifiers=verifiers,
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
