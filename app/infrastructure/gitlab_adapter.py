"""GitLab adapter for incident-report pages and actionable issues."""

from urllib.parse import quote

import httpx

from domain.actions.ports import ActionItemPort
from domain.reporting.ports import IncidentReport, IncidentReportPort, ReportReference
from infrastructure.http_client import AsyncRestClient, ExternalServiceError


class GitLabAdapter(IncidentReportPort, ActionItemPort):
    """Works with gitlab.com and self-managed/private GitLab installations."""

    def __init__(
        self, base_url: str, token: str, project_id: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._project_id = project_id
        self._project_path = quote(project_id, safe="")
        self._client = AsyncRestClient(
            service="GitLab", base_url=f"{self._base_url}/api/v4",
            headers={"PRIVATE-TOKEN": token, "Accept": "application/json"},
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def create_report(self, report: IncidentReport) -> dict:
        title = f"Incident report: {report.title.strip()}"
        page = await self._client.request(
            "POST", f"/projects/{self._project_path}/wikis",
            data={"title": title, "content": self._render_template(report)},
        )
        return {
            "provider": "gitlab", "report_id": page["slug"],
            "title": page["title"],
            "url": f"{self._base_url}/{self._project_id}/-/wikis/{quote(page['slug'], safe='')}",
        }

    async def get_report(self, report_id: str) -> ReportReference | None:
        try:
            page = await self._client.request(
                "GET", f"/projects/{self._project_path}/wikis/{quote(report_id, safe='')}",
            )
        except ExternalServiceError as exc:
            if exc.status_code == 404:
                return None
            raise
        return ReportReference(
            provider="gitlab", report_id=page["slug"],
            url=f"{self._base_url}/{self._project_id}/-/wikis/{quote(page['slug'], safe='')}",
        )

    async def create_action(
        self, description: str, assignee: str, priority: str,
        report: ReportReference, title: str,
    ) -> dict:
        users = await self._client.request("GET", "/users", params={"username": assignee})
        if not isinstance(users, list) or len(users) != 1:
            raise ValueError("The GitLab assignee must resolve to exactly one username.")
        user = users[0]

        labels = f"incident-action,priority::{priority}"
        issue = await self._client.request(
            "POST", f"/projects/{self._project_path}/issues",
            data={
                "title": title.strip() or f"Incident action: {description.splitlines()[0]}",
                "description": f"{description}\n\nRelated incident report: {report.url}",
                "assignee_ids[]": str(user["id"]), "labels": labels,
            },
        )
        return {
            "issue_id": str(issue["iid"]), "issue_key": f"{self._project_id}#{issue['iid']}",
            "url": issue["web_url"], "assignee": assignee, "priority": priority,
            "related_report_id": report.report_id, "remote_link_id": "description",
        }

    @staticmethod
    def _render_template(report: IncidentReport) -> str:
        # Markdown preserves line breaks and user text without embedding HTML.
        def section(title: str, text: str) -> str:
            return f"\n## {title}\n\n{text.strip()}\n"

        return (
            "# Incident report\n\n"
            f"**Created by:** {report.created_by}  \n"
            f"**Created at (UTC):** {report.created_at.isoformat()}\n\n"
            "*Blameless review: focus on system and process improvements.*"
            + section("Summary", report.summary)
            + section("Impact", report.impact)
            + section("Root cause", report.root_cause)
            + section("Timeline", report.timeline)
            + section("Resolution", report.resolution)
            + section("Follow-up actions", "Create action items linked to this report.")
        )
