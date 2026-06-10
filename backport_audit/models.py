from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class AuditStatus(str, Enum):
    OPEN_OR_UNRESOLVED = "OPEN_OR_UNRESOLVED"
    CLOSED_NO_PR = "CLOSED_NO_PR"
    PR_NOT_MERGED = "PR_NOT_MERGED"
    BACKPORTED_CONFIRMED = "BACKPORTED_CONFIRMED"
    PROBABLY_BACKPORTED = "PROBABLY_BACKPORTED"
    NOT_BACKPORTED = "NOT_BACKPORTED"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    ERROR = "ERROR"


@dataclass(frozen=True)
class JiraIssue:
    key: str
    summary: str
    status: str
    resolution: str | None
    fix_versions: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    description: str = ""
    comments: list[str] = field(default_factory=list)
    remote_links: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PullRequestRef:
    repo: str
    number: int
    url: str


@dataclass
class PullRequestDetails:
    ref: PullRequestRef
    title: str
    body: str
    state: str
    merged: bool
    merge_commit_sha: str | None
    base_branch: str
    commits: list[str] = field(default_factory=list)
    commit_subjects: dict[str, str] = field(default_factory=dict)
    changed_files: list[str] = field(default_factory=list)


@dataclass
class VerificationResult:
    status: AuditStatus
    method: str
    evidence: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class IssueAuditResult:
    issue: JiraIssue
    pull_requests: list[PullRequestDetails]
    verification: VerificationResult


@dataclass
class AuditSummary:
    fix_version: str
    target_branch: str
    closed_status: str
    total_bugs: int
    closed_bugs: int
    not_closed_bugs: int
    closed_with_pr_backported: int
    closed_with_pr_not_backported: int
    closed_without_pr: int
