"""Jira Cloud / Data Center v2 adapter using only the public REST API."""

from urllib.parse import quote

import httpx

from domain.actions.ports import ActionItemPort
from domain.reporting.ports import ReportReference
from infrastructure.http_client import AsyncRestClient


class JiraActionItemAdapter(ActionItemPort):
    def __init__(
        self, base_url: str, api_token: str, project_key: str,
        issue_type: str = "Task", email: str | None = None,
        cloud: bool = True, transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._project_key = project_key
        self._issue_type = issue_type
        self._cloud = cloud
        authorization = (
            httpx.BasicAuth(email, api_token).headers["Authorization"]
            if cloud else f"Bearer {api_token}"
        )
        self._client = AsyncRestClient(
            service="Jira", base_url=f"{self._base_url}/rest/api/2",
            headers={"Authorization": authorization, "Accept": "application/json"},
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def create_action(
        self, description: str, assignee: str, priority: str,
        report: ReportReference, title: str,
    ) -> dict:
        summary = title.strip() or self._summary_from(description)
        issue = await self._client.request("POST", "/issue", json={
            "fields": {
                "project": {"key": self._project_key},
                "summary": summary,
                "description": self._description(description, report),
                "issuetype": {"name": self._issue_type},
                "priority": {"name": priority},
                # Jira Cloud uses accountId; Data Center commonly uses name.
                "assignee": {"accountId" if self._cloud else "name": assignee},
            },
        })
        issue_key = issue.get("key")
        if not issue_key:
            raise ValueError("Jira returned no issue key.")

        report_url = report.url
        link = await self._client.request("POST", f"/issue/{quote(issue_key, safe='')}/remotelink", json={
            "object": {
                "url": report_url,
                "title": f"Incident report ({report.provider}: {report.report_id})",
            },
            "relationship": "relates to",
        })
        return {
            "issue_id": issue["id"],
            "issue_key": issue_key,
            "url": f"{self._base_url}/browse/{quote(issue_key, safe='')}",
            "assignee": assignee,
            "priority": priority,
            "related_report_id": report.report_id,
            "remote_link_id": str(link["id"]),
        }

    @staticmethod
    def _summary_from(description: str) -> str:
        first_line = description.strip().splitlines()[0]
        return f"Incident action: {first_line}"[:255]

    def _description(self, description: str, report: ReportReference) -> str | dict:
        reference = f"Related incident report ({report.provider}): {report.url}"
        if not self._cloud:
            return f"{description}\n\n{reference}"
        # Atlassian Document Format is required by Jira Cloud v2 issue create.
        return {
            "type": "doc", "version": 1,
            "content": [
                self._paragraph(description),
                self._paragraph(reference),
            ],
        }

    @staticmethod
    def _paragraph(text: str) -> dict:
        return {"type": "paragraph", "content": [{"type": "text", "text": text}]}
