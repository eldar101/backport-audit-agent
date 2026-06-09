from pathlib import Path

from backport_audit.config import (
    is_placeholder_secret,
    normalize_url,
    parse_gh_auth_status_token,
    read_netrc_auth,
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


def test_parse_gh_auth_status_token():
    output = """
github.com
  - Token: gho_example
"""

    assert parse_gh_auth_status_token(output) == "gho_example"


def test_is_placeholder_secret_detects_copy_paste_tokens():
    assert is_placeholder_secret("YOUR_JIRA_TOKEN")
    assert is_placeholder_secret("paste_token_here")
    assert not is_placeholder_secret("ATATT3x-real-looking-token")


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


def test_read_netrc_auth(monkeypatch, tmp_path: Path):
    netrc_file = tmp_path / ".netrc"
    netrc_file.write_text(
        "machine jira.example.com login user@example.com password token-123\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("NETRC", str(netrc_file))

    assert read_netrc_auth("https://jira.example.com") == ("user@example.com", "token-123")
