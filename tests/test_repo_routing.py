from pathlib import Path

import pytest

from backport_audit.models import JiraIssue
from backport_audit.repo_routing import default_clone_dir, parse_repo_route, select_repo_for_issue


def test_parse_repo_route():
    route = parse_repo_route("[UI]=owner/ui")

    assert route.marker == "[UI]"
    assert route.repo == "owner/ui"


def test_parse_repo_route_rejects_invalid_repo():
    with pytest.raises(ValueError, match="owner/repo"):
        parse_repo_route("[UI]=owner/ui/extra")


def test_parse_repo_route_rejects_bad_format():
    with pytest.raises(ValueError):
        parse_repo_route("[UI]")


def test_select_repo_for_issue_matches_summary_marker():
    issue = JiraIssue(
        key="PROJ-1",
        summary="[UI] Fix empty state",
        status="Closed",
        resolution=None,
    )

    route = parse_repo_route("[UI]=owner/ui")

    assert select_repo_for_issue(issue, "owner/backend", [route]) == "owner/ui"


def test_select_repo_for_issue_matches_marker_text_without_brackets():
    issue = JiraIssue(
        key="PROJ-1",
        summary="UI - Fix empty state",
        status="Closed",
        resolution=None,
    )

    route = parse_repo_route("[UI]=owner/ui")

    assert select_repo_for_issue(issue, "owner/backend", [route]) == "owner/ui"


def test_default_clone_dir_uses_repo_specific_subdir_for_base_dir():
    assert default_clone_dir(Path("/tmp/clones"), Path(".cache"), "owner/ui") == Path(
        "/tmp/clones/owner-ui"
    )
