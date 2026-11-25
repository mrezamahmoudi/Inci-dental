"""Confluence Cloud v2 adapter for templated incident reports."""

import html
from urllib.parse import quote

import httpx

from domain.reporting.ports import (
    IncidentReport, IncidentReportPort, ReportReference,
)
from infrastructure.http_client import AsyncRestClient, ExternalServiceError


class ConfluenceIncidentReportAdapter(IncidentReportPort):
    def __init__(
        self, base_url: str, email: str, api_token: str, space_id: str,
        parent_page_id: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._space_id = space_id
        self._parent_page_id = parent_page_id
        self._client = AsyncRestClient(
            service="Confluence", base_url=f"{self._base_url}/wiki/api/v2",
            headers={
                "Authorization": httpx.BasicAuth(email, api_token).headers["Authorization"],
                "Accept": "application/json",
            }, transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def create_report(self, report: IncidentReport) -> dict:
        title = f"Incident report: {report.title.strip()}"
        payload = {
            "spaceId": self._space_id,
            "status": "current",
            "title": title,
            "body": {
                "representation": "storage",
                "value": self._render_template(report),
            },
        }
        if self._parent_page_id:
            payload["parentId"] = self._parent_page_id
        page = await self._client.request("POST", "/pages", json=payload)
        return {
            "provider": "confluence", "report_id": page["id"],
            "title": page.get("title", title), "url": self._page_url(page),
        }

    async def get_report(self, report_id: str) -> ReportReference | None:
        if not report_id.isdigit():
            return None
        try:
            page = await self._client.request(
                "GET", f"/pages/{quote(report_id, safe='')}",
            )
            return ReportReference(
                provider="confluence", report_id=page["id"], url=self._page_url(page),
            )
        except ExternalServiceError as exc:
            if exc.status_code == 404:
                return None
            raise

    def _page_url(self, page: dict) -> str:
        # Cloud's v2 response supplies a relative webui path.
        webui = page.get("_links", {}).get("webui")
        return f"{self._base_url}/wiki{webui}" if webui else f"{self._base_url}/wiki/pages/{page['id']}"

    @staticmethod
    def _render_template(report: IncidentReport) -> str:
        def section(heading: str, text: str) -> str:
            escaped = html.escape(text.strip(), quote=False)
            # Preserve user line breaks without interpreting supplied text as HTML.
            return f"<h2>{heading}</h2><p>{escaped.replace(chr(10), '<br/>')}</p>"

        return (
            "<h1>Incident report</h1>"
            f"<p><strong>Created by:</strong> {html.escape(report.created_by)}<br/>"
            f"<strong>Created at (UTC):</strong> {report.created_at.isoformat()}</p>"
            "<p><em>Blameless review: focus on system and process improvements.</em></p>"
            + section("Summary", report.summary)
            + section("Impact", report.impact)
            + section("Root cause", report.root_cause)
            + section("Timeline", report.timeline)
            + section("Resolution", report.resolution)
            + section("Follow-up actions", "Create Jira action items linked to this report.")
        )
