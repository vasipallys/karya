"""Small async Jira REST v3/v2 wrapper using httpx."""

from __future__ import annotations

import re
from typing import Any

import httpx

from backend.config import JiraInstanceSettings
from backend.jira.mapping import issue_to_story
from backend.models import Story


class JiraError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, retryable: bool = False) -> None:
        self.status = status
        self.retryable = retryable
        super().__init__(message)


class JiraClient:
    """Read Jira issues and perform an explicitly gated points update."""

    def __init__(self, config: JiraInstanceSettings) -> None:
        self.config = config

    def _headers_and_auth(self) -> tuple[dict[str, str], httpx.Auth | None]:
        token = self.config.api_token.get_secret_value()
        if self.config.auth_type == "cloud":
            return {"Accept": "application/json"}, httpx.BasicAuth(self.config.email or "", token)
        return {"Accept": "application/json", "Authorization": f"Bearer {token}"}, None

    @property
    def api_version(self) -> str:
        return "3" if self.config.auth_type == "cloud" else "2"

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        headers, auth = self._headers_and_auth()
        url = f"{self.config.base_url}/rest/api/{self.api_version}/{path.lstrip('/')}"
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=30, headers=headers, auth=auth) as client:
                    response = await client.request(method, url, **kwargs)
                if response.status_code >= 400:
                    detail = response.json() if "json" in response.headers.get("content-type", "") else response.text
                    retryable = response.status_code in {429, 502, 503, 504}
                    if retryable and attempt == 0:
                        continue
                    raise JiraError(
                        f"Jira returned {response.status_code}: {detail}",
                        status=response.status_code,
                        retryable=retryable,
                    )
                return response.json() if response.content else {}
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = exc
                if attempt == 0:
                    continue
        raise JiraError(f"Could not reach Jira: {last_error}", retryable=True)

    async def health(self) -> dict[str, Any]:
        try:
            await self._request("GET", "myself")
            return {"status": "ok", "message": "Connected"}
        except JiraError as exc:
            return {"status": "error", "message": str(exc), "retryable": exc.retryable}

    async def fetch_project_issues(
        self,
        project_code: str,
        *,
        status: str | None = None,
        sprint: str | None = None,
        page_size: int = 50,
        max_issues: int = 500,
    ) -> list[Story]:
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,49}", project_code):
            raise JiraError("Project code contains invalid characters")
        clauses = [f'project = "{project_code}"']
        if status:
            clauses.append(f'status = "{status.replace(chr(34), chr(92) + chr(34))}"')
        if sprint:
            clauses.append(f'sprint = "{sprint.replace(chr(34), chr(92) + chr(34))}"')
        jql = " AND ".join(clauses) + " ORDER BY created DESC"
        fields = ["summary", "description", "status", "labels", "components"]
        if self.config.story_points_field:
            fields.append(self.config.story_points_field)
        if self.config.ac_field:
            fields.append(self.config.ac_field)

        stories: list[Story] = []
        start_at = 0
        next_page_token: str | None = None
        while len(stories) < max_issues:
            size = min(page_size, max_issues - len(stories))
            params = {"jql": jql, "maxResults": size, "fields": ",".join(fields)}
            if self.config.auth_type == "cloud":
                if next_page_token:
                    params["nextPageToken"] = next_page_token
                payload = await self._request("GET", "search/jql", params=params)
            else:
                params["startAt"] = start_at
                payload = await self._request("GET", "search", params=params)
            issues = payload.get("issues") or []
            stories.extend(issue_to_story(issue, self.config) for issue in issues)
            start_at += len(issues)
            if self.config.auth_type == "cloud":
                next_page_token = payload.get("nextPageToken")
                if not issues or payload.get("isLast") is True or not next_page_token:
                    break
            elif not issues or start_at >= payload.get("total", 0):
                break
        return stories

    async def create_issue(self, project_key: str, issue_type: str, summary: str, description: str = "") -> str:
        fields: dict[str, Any] = {
            "project": {"key": project_key},
            "issuetype": {"name": issue_type},
            "summary": summary[:255],
        }
        if description:
            if self.config.auth_type == "cloud":
                # REST v3 requires Atlassian Document Format for rich-text fields.
                fields["description"] = {
                    "type": "doc",
                    "version": 1,
                    "content": [{"type": "paragraph", "content": [{"type": "text", "text": description}]}],
                }
            else:
                fields["description"] = description
        payload = await self._request("POST", "issue", json={"fields": fields})
        key = payload.get("key")
        if not key:
            raise JiraError("Jira accepted the issue but returned no key")
        return key

    async def write_points(self, issue_key: str, points: int) -> None:
        field = self.config.story_points_field
        if not field:
            raise JiraError("Story Points field is not configured for this Jira instance")
        await self._request("PUT", f"issue/{issue_key}", json={"fields": {field: points}})
