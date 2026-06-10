from __future__ import annotations

from urllib.parse import quote

import requests

from backport_audit.models import PullRequestDetails, PullRequestRef


class GitHubClient:
    def __init__(self, token: str) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )

    def get_pr(self, ref: PullRequestRef) -> PullRequestDetails:
        pr = self._get(f"https://api.github.com/repos/{ref.repo}/pulls/{ref.number}")
        commits = self._get_paginated(
            f"https://api.github.com/repos/{ref.repo}/pulls/{ref.number}/commits"
        )
        files = self._get_paginated(
            f"https://api.github.com/repos/{ref.repo}/pulls/{ref.number}/files"
        )
        commit_shas = [commit["sha"] for commit in commits]
        subjects = {
            commit["sha"]: (commit.get("commit", {}).get("message", "").splitlines() or [""])[0]
            for commit in commits
        }
        return PullRequestDetails(
            ref=ref,
            title=pr.get("title") or "",
            body=pr.get("body") or "",
            author=(pr.get("user") or {}).get("login") or "",
            state=pr.get("state") or "",
            merged=bool(pr.get("merged")),
            merge_commit_sha=pr.get("merge_commit_sha"),
            base_branch=(pr.get("base") or {}).get("ref") or "",
            commits=commit_shas,
            commit_subjects=subjects,
            changed_files=[item.get("filename", "") for item in files if item.get("filename")],
        )

    def search_prs(
        self,
        repo: str,
        query: str,
        base_branch: str | None = None,
    ) -> list[PullRequestRef]:
        parts = [f"repo:{repo}", "is:pr", query]
        if base_branch:
            parts.append(f"base:{base_branch}")
        raw_query = " ".join(parts)
        url = f"https://api.github.com/search/issues?q={quote(raw_query)}"
        data = self._get(url)
        refs: list[PullRequestRef] = []
        for item in data.get("items", []):
            if "pull_request" not in item:
                continue
            refs.append(PullRequestRef(repo=repo, number=item["number"], url=item["html_url"]))
        return refs

    def search_commits(self, repo: str, query: str) -> list[str]:
        url = f"https://api.github.com/search/commits?q={quote(f'repo:{repo} {query}')}"
        response = self.session.get(url, headers={"Accept": "application/vnd.github.cloak-preview"})
        response.raise_for_status()
        return [item["sha"] for item in response.json().get("items", [])]

    def _get(self, url: str) -> dict:
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()

    def _get_paginated(self, url: str) -> list[dict]:
        items: list[dict] = []
        next_url: str | None = url
        while next_url:
            response = self.session.get(next_url, params={"per_page": 100})
            response.raise_for_status()
            items.extend(response.json())
            next_url = response.links.get("next", {}).get("url")
        return items
