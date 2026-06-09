from backport_audit.config import derive_target_branch
from backport_audit.pr_discovery import extract_pr_refs


def test_derive_target_branch_from_rc_fix_version():
    assert derive_target_branch("1.2.0-rc1") == "release-1.2"


def test_extract_pr_refs_from_github_urls():
    refs = extract_pr_refs("Fixed by https://github.com/flightctl/flightctl/pull/3012")

    assert len(refs) == 1
    assert refs[0].repo == "flightctl/flightctl"
    assert refs[0].number == 3012
