from __future__ import annotations

import getpass
import os
from dataclasses import dataclass

from rich.console import Console


@dataclass(frozen=True)
class RuntimeConfig:
    jira_base_url: str
    jira_user: str | None
    jira_token: str
    github_token: str
    github_repo: str
    fix_version: str
    target_branch: str
    jira_project: str | None = None
    clone_dir: str | None = None


def derive_target_branch(fix_version: str) -> str:
    version = fix_version.split("-")[0]
    parts = version.split(".")
    if len(parts) < 2:
        raise ValueError(
            f"Cannot derive release branch from fixVersion '{fix_version}'. "
            "Pass --target-branch explicitly."
        )
    return f"release-{parts[0]}.{parts[1]}"


def prompt_missing_auth(
    *,
    jira_base_url: str,
    jira_user: str | None,
    github_token: str | None,
    jira_token: str | None,
    console: Console,
) -> tuple[str | None, str, str]:
    if not jira_user:
        env_user = os.getenv("JIRA_USER") or os.getenv("JIRA_EMAIL")
        jira_user = env_user or console.input("Jira username/email: ").strip()

    if not jira_token:
        console.print(
            "[yellow]JIRA_TOKEN is not set.[/yellow] "
            "Enter a Jira API token or Personal Access Token. It will not be saved."
        )
        jira_token = getpass.getpass(f"Jira token for {jira_base_url}: ").strip()

    if not github_token:
        console.print(
            "[yellow]GITHUB_TOKEN is not set.[/yellow] "
            "Enter a GitHub token with repo read access. It will not be saved."
        )
        github_token = getpass.getpass("GitHub token: ").strip()

    if not jira_token:
        raise ValueError("Jira token is required.")
    if not github_token:
        raise ValueError("GitHub token is required.")

    return jira_user, jira_token, github_token
