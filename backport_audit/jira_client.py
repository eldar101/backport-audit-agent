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

    def search_bugs(
        self,
        fix_version: str,
        project: str | None = None,
        issue_type: str | None = None,
        jql_override: str | None = None,
    ) -> list[JiraIssue]:
        jql = jql_override or build_jql(
            fix_version=fix_version,
            project=project,
            issue_type=issue_type,
        )

        try:
            return self._search_bugs_cloud(jql)
        except LegacySearchRequired:
            return self._search_bugs_legacy(jql)

    def count_issues(self, jql: str) -> int:
        try:
            return self._count_issues_cloud(jql)
        except LegacySearchRequired:
            return self._count_issues_legacy(jql)

    @staticmethod
    def build_jql(
        *,
        fix_version: str,
        project: str | None = None,
        issue_type: str | None = None,
    ) -> str:
        return build_jql(fix_version=fix_version, project=project, issue_type=issue_type)

    def _search_bugs_cloud(self, jql: str) -> list[JiraIssue]:
        issues: list[JiraIssue] = []
        next_page_token: str | None = None
        max_results = 100

        while True:
            payload = {
                "jql": jql,
                "maxResults": max_results,
                "fields": search_fields(),
            }
            if next_page_token:
                payload["nextPageToken"] = next_page_token

            response = self.session.post(
                urljoin(self.base_url, "rest/api/3/search/jql"),
                json=payload,
            )
            if response.status_code in {404, 405, 410}:
                raise LegacySearchRequired
            response.raise_for_status()
            data = response.json()
            raw_issues = data.get("issues", [])
            for raw_issue in raw_issues:
                issues.append(self._parse_issue(raw_issue))

            next_page_token = data.get("nextPageToken")
            if data.get("isLast", True) or not next_page_token or not raw_issues:
                break

        return issues

    def _count_issues_cloud(self, jql: str) -> int:
        response = self.session.post(
            urljoin(self.base_url, "rest/api/3/search/approximate-count"),
            json={"jql": jql},
        )
        if response.status_code in {404, 405, 410}:
            raise LegacySearchRequired
        response.raise_for_status()
        return int(response.json().get("count", 0))

    def _search_bugs_legacy(self, jql: str) -> list[JiraIssue]:
        issues: list[JiraIssue] = []
        start_at = 0
        max_results = 100
        while True:
            payload = {
                "jql": jql,
                "startAt": start_at,
                "maxResults": max_results,
                "fields": search_fields(),
            }
            response = self.session.post(urljoin(self.base_url, "rest/api/2/search"), json=payload)
            response.raise_for_status()
            data = response.json()
            raw_issues = data.get("issues", [])
            for raw_issue in raw_issues:
                issues.append(self._parse_issue(raw_issue))

            start_at += len(raw_issues)
            if start_at >= data.get("total", 0) or not raw_issues:
                break

        return issues

    def _count_issues_legacy(self, jql: str) -> int:
        response = self.session.post(
            urljoin(self.base_url, "rest/api/2/search"),
            json={"jql": jql, "startAt": 0, "maxResults": 0, "fields": []},
        )
        response.raise_for_status()
        return int(response.json().get("total", 0))

    def get_remote_links(self, issue_key: str) -> list[str]:
        response = self.session.get(
            urljoin(self.base_url, f"rest/api/3/issue/{issue_key}/remotelink")
        )
        if response.status_code in {404, 405, 410}:
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
            jira_text(comment.get("body", ""))
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
            description=jira_text(fields.get("description") or ""),
            comments=comments,
            remote_links=[],
        )


class LegacySearchRequired(Exception):
    pass


def build_jql(
    *,
    fix_version: str,
    project: str | None = None,
    issue_type: str | None = None,
) -> str:
    jql_parts = [f'fixVersion in ("{fix_version}")']
    if issue_type:
        jql_parts.append(f'issuetype = "{issue_type}"')
    if project:
        jql_parts.insert(0, f"project = {project}")
    return " AND ".join(jql_parts)


def add_status_filter(jql: str, status: str) -> str:
    base_jql, order_by = split_order_by(jql)
    status_filter = f'status = "{status}"'
    filtered = f"{base_jql} AND {status_filter}"
    if order_by:
        return f"{filtered} {order_by}"
    return filtered


def split_order_by(jql: str) -> tuple[str, str]:
    marker = " ORDER BY "
    upper = jql.upper()
    index = upper.rfind(marker)
    if index == -1:
        return jql.strip(), ""
    return jql[:index].strip(), jql[index:].strip()


def search_fields() -> list[str]:
    return [
        "summary",
        "status",
        "resolution",
        "fixVersions",
        "description",
        "comment",
    ]


def jira_text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(part for part in (jira_text(item) for item in value) if part)
    if not isinstance(value, dict):
        return ""

    if isinstance(value.get("text"), str):
        return value["text"]
    if isinstance(value.get("content"), list):
        return jira_text(value["content"])
    if isinstance(value.get("value"), str):
        return value["value"]
    return ""
