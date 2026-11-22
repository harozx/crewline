"""Read-only Jira client (REST v2: works on Cloud and Data Center/Server). Anonymous for public instances."""

from __future__ import annotations

import os
from collections.abc import Iterator

import httpx

FIELDS = "summary,description,created,resolutiondate,issuetype,components,priority,attachment,issuelinks"


class Jira:
    def __init__(self, base_url: str, token: str | None = None, user: str | None = None):
        token = token or os.environ.get("JIRA_TOKEN")
        user = user or os.environ.get("JIRA_USER")
        headers = {"Accept": "application/json"}
        auth = None
        if token and user:          # Cloud: email + API token
            auth = (user, token)
        elif token:                 # Data Center: personal access token
            headers["Authorization"] = f"Bearer {token}"
        self.base = base_url.rstrip("/")
        self.http = httpx.Client(headers=headers, auth=auth, timeout=60, follow_redirects=True)

    def search(self, jql: str, fields: str = FIELDS, page: int = 100) -> Iterator[dict]:
        start = 0
        while True:
            r = self.http.get(f"{self.base}/rest/api/2/search",
                              params={"jql": jql, "fields": fields, "startAt": start, "maxResults": page})
            r.raise_for_status()
            body = r.json()
            issues = body.get("issues", [])
            yield from issues
            start += len(issues)
            if not issues or start >= body.get("total", 0):
                return

    def issue(self, key: str, fields: str = FIELDS + ",comment") -> dict:
        r = self.http.get(f"{self.base}/rest/api/2/issue/{key}", params={"fields": fields})
        r.raise_for_status()
        return r.json()


def flatten(issue: dict) -> dict:
    f = issue.get("fields", {})
    return {
        "key": issue["key"],
        "summary": f.get("summary") or "",
        "description": f.get("description") or "",
        "created": f.get("created"),
        "resolved": f.get("resolutiondate"),
        "type": (f.get("issuetype") or {}).get("name"),
        "components": [c.get("name") for c in f.get("components") or []],
        "attachments": [a.get("filename") for a in f.get("attachment") or []],
    }
