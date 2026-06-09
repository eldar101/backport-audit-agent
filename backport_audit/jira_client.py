from __future__ import annotations

from urllib.parse import urljoin

import requests

from backport_audit.models import JiraIssue


class JiraClient:
    def __init__(self, base_url: str, user: str | None, token: str) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        if user:
            self.session.auth = (user, token)
        else:
            self.session.headers.update({"Authorization": f"Bearer {token}"})

    def search_bugs(self, fix_version: str, project: str | None = None) -> list[JiraIssue]:
        jql_parts = [f'fixVersion in ("{fix_version}")', "issuetype = Bug"]
        if project:
            jql_parts.insert(0, f"project = {project}")
        jql = " AND ".join(jql_parts)

        issues: list[JiraIssue] = []
        start_at = 0
        max_results = 100
        while True:
            payload = {
                "jql": jql,
                "startAt": start_at,
                "maxResults": max_results,
                "fields": [
                    "summary",
                    "status",
                    "resolution",
                    "fixVersions",
                    "description",
                    "comment",
                ],
            }
            response = self.session.post(urljoin(self.base_url, "rest/api/2/search"), json=payload)
            response.raise_for_status()
            data = response.json()
            for raw_issue in data.get("issues", []):
                issue = self._parse_issue(raw_issue)
                issue.remote_links.extend(self.get_remote_links(issue.key))
                issues.append(issue)

            start_at += len(data.get("issues", []))
            if start_at >= data.get("total", 0) or not data.get("issues"):
                break

        return issues

    def get_remote_links(self, issue_key: str) -> list[str]:
        response = self.session.get(
            urljoin(self.base_url, f"rest/api/2/issue/{issue_key}/remotelink")
        )
        response.raise_for_status()
        links: list[str] = []
        for raw_link in response.json():
            obj = raw_link.get("object") or {}
            url = obj.get("url")
            if url:
                links.append(url)
        return links

    @staticmethod
    def _parse_issue(raw_issue: dict) -> JiraIssue:
        fields = raw_issue.get("fields", {})
        comments = [
            comment.get("body", "")
            for comment in (fields.get("comment") or {}).get("comments", [])
            if comment.get("body")
        ]
        return JiraIssue(
            key=raw_issue["key"],
            summary=(fields.get("summary") or "").strip(),
            status=((fields.get("status") or {}).get("name") or "").strip(),
            resolution=(fields.get("resolution") or {}).get("name")
            if fields.get("resolution")
            else None,
            fix_versions=[item.get("name", "") for item in fields.get("fixVersions", [])],
            description=fields.get("description") or "",
            comments=comments,
            remote_links=[],
        )
