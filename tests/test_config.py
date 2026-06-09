from pathlib import Path

from backport_audit.config import (
    normalize_url,
    read_simple_yaml_mapping,
    resolve_github_token,
    resolve_jira_base_url,
    resolve_jira_token,
    resolve_jira_user,
)


def test_normalize_url_adds_https():
    assert normalize_url("jira.example.com/") == "https://jira.example.com"


def test_resolve_jira_values_from_common_env(monkeypatch):
    monkeypatch.setenv("JIRA_URL", "jira.example.com")
    monkeypatch.setenv("JIRA_USERNAME", "user@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "jira-token")

    assert resolve_jira_base_url() == "https://jira.example.com"
    assert resolve_jira_user() == "user@example.com"
    assert resolve_jira_token() == "jira-token"


def test_resolve_github_token_prefers_env(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "gh-token")

    assert resolve_github_token() == "gh-token"


def test_read_simple_yaml_mapping(tmp_path: Path):
    config = tmp_path / "config.yml"
    config.write_text(
        """
endpoint: https://jira.example.com
login: user@example.com
token: abc123
""",
        encoding="utf-8",
    )

    assert read_simple_yaml_mapping(config) == {
        "endpoint": "https://jira.example.com",
        "login": "user@example.com",
        "token": "abc123",
    }
