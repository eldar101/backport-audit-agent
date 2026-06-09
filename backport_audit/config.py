from __future__ import annotations

import getpass
import netrc
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

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


def first_env(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value.strip()
    return None


def resolve_jira_base_url(explicit_url: str | None = None) -> str | None:
    value = explicit_url or first_env(
        "JIRA_BASE_URL",
        "JIRA_URL",
        "JIRA_SERVER",
        "ATLASSIAN_SITE",
    )
    if value:
        return normalize_url(value)

    config = read_jira_cli_config()
    endpoint = config.get("endpoint") or config.get("server") or config.get("url")
    return normalize_url(endpoint) if endpoint else None


def resolve_jira_user(
    explicit_user: str | None = None,
    *,
    jira_base_url: str | None = None,
) -> str | None:
    if explicit_user:
        return explicit_user
    value = first_env("JIRA_USER", "JIRA_EMAIL", "JIRA_USERNAME", "ATLASSIAN_EMAIL")
    if value:
        return value

    netrc_auth = read_netrc_auth(jira_base_url)
    if netrc_auth and netrc_auth[0]:
        return netrc_auth[0]

    config = read_jira_cli_config()
    return (
        config.get("login")
        or config.get("user")
        or config.get("username")
        or config.get("email")
    )


def resolve_jira_token(
    explicit_token: str | None = None,
    *,
    jira_base_url: str | None = None,
) -> str | None:
    if explicit_token:
        return explicit_token
    value = first_env(
        "JIRA_TOKEN",
        "JIRA_API_TOKEN",
        "JIRA_PERSONAL_ACCESS_TOKEN",
        "ATLASSIAN_API_TOKEN",
    )
    if value:
        return value

    netrc_auth = read_netrc_auth(jira_base_url)
    if netrc_auth and netrc_auth[1]:
        return netrc_auth[1]

    config = read_jira_cli_config()
    return (
        config.get("token")
        or config.get("access-token")
        or config.get("access_token")
        or config.get("password")
    )


def resolve_github_token(explicit_token: str | None = None) -> str | None:
    if explicit_token:
        return explicit_token
    value = first_env("GITHUB_TOKEN", "GH_TOKEN")
    if value:
        return value
    return read_gh_auth_token()


def normalize_url(value: str) -> str:
    value = value.strip().rstrip("/")
    if value and not re.match(r"^https?://", value):
        value = f"https://{value}"
    return value


def read_gh_auth_token() -> str | None:
    result = subprocess.run(
        ["gh", "auth", "token"],
        check=False,
        text=True,
        capture_output=True,
    )
    if result.returncode == 0:
        token = result.stdout.strip()
        if token:
            return token

    status = subprocess.run(
        ["gh", "auth", "status", "--show-token"],
        check=False,
        text=True,
        capture_output=True,
    )
    if status.returncode != 0:
        return None
    return parse_gh_auth_status_token(status.stdout + status.stderr)


def parse_gh_auth_status_token(output: str) -> str | None:
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("- Token:"):
            token = stripped.removeprefix("- Token:").strip()
            return token or None
    return None


def read_jira_cli_config() -> dict[str, str]:
    configured_path = first_env("JIRA_CONFIG_FILE")
    paths = [
        Path(configured_path).expanduser() if configured_path else None,
        Path.home() / ".config" / ".jira" / ".config.yml",
        Path.home() / ".jira.d" / "config.yml",
        Path.home() / ".jira" / "config.yml",
        Path.home() / ".config" / "jira" / "config.yml",
        Path.home() / ".config" / "jira" / "config.yaml",
    ]
    merged: dict[str, str] = {}
    for path in paths:
        if path:
            merged.update(read_simple_yaml_mapping(path))
    return merged


def read_simple_yaml_mapping(path: Path) -> dict[str, str]:
    if not path.exists() or not path.is_file():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip().strip("'\"")
        if key and value and not value.startswith("{"):
            values[key] = value
    return values


def read_netrc_auth(jira_base_url: str | None) -> tuple[str | None, str | None] | None:
    if not jira_base_url:
        return None

    host = urlparse(normalize_url(jira_base_url)).hostname
    if not host:
        return None

    try:
        netrc_path = first_env("NETRC")
        auth = netrc.netrc(netrc_path).authenticators(host)
    except (FileNotFoundError, netrc.NetrcParseError):
        return None

    if not auth:
        return None

    login, _, password = auth
    return login, password


def prompt_missing_auth(
    *,
    jira_base_url: str,
    jira_user: str | None,
    github_token: str | None,
    jira_token: str | None,
    console: Console,
) -> tuple[str | None, str, str]:
    if not jira_user:
        jira_user = console.input(
            "Jira username/email (leave empty for bearer-token auth): "
        ).strip()
        jira_user = jira_user or None

    if not jira_token:
        console.print(
            "[yellow]No Jira token was found in the environment or Jira CLI config.[/yellow] "
            "Enter a Jira API token or Personal Access Token. It will not be saved."
        )
        jira_token = getpass.getpass(f"Jira token for {jira_base_url}: ").strip()

    if not github_token:
        console.print(
            "[yellow]No GitHub token was found in the environment or gh auth.[/yellow] "
            "Enter a GitHub token with repo read access. It will not be saved."
        )
        github_token = getpass.getpass("GitHub token: ").strip()

    if not jira_token:
        raise ValueError("Jira token is required.")
    if not github_token:
        raise ValueError("GitHub token is required.")

    return jira_user, jira_token, github_token
