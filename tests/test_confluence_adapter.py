import json
from datetime import datetime, timezone

import httpx
import pytest

from domain.reporting.ports import IncidentReport
from infrastructure.http_client import ExternalServiceError
from infrastructure.reporting.confluence_adapter import ConfluenceIncidentReportAdapter


def report():
    return IncidentReport(
        title="API outage <severity-1>", summary="API was unavailable.",
        impact="Users could not sign in.", root_cause="Database failover <failed>.",
        timeline="12:00 detected\n12:10 mitigated", resolution="Restored primary.",
        created_by="operator", created_at=datetime(2026, 11, 25, tzinfo=timezone.utc),
    )


async def test_confluence_creates_escaped_templated_v2_page():
    requests = []

    def handler(request):
        requests.append(request)
        if request.method == "POST":
            payload = json.loads(request.content)
            assert payload["spaceId"] == "12345"
            assert "<h2>Root cause</h2>" in payload["body"]["value"]
            assert "&lt;failed&gt;" in payload["body"]["value"]
            assert "Database failover <failed>" not in payload["body"]["value"]
            return httpx.Response(200, json={
                "id": "987", "title": payload["title"],
                "_links": {"webui": "/spaces/OPS/pages/987"},
            })
        return httpx.Response(200, json={"id": "987"})

    adapter = ConfluenceIncidentReportAdapter(
        "https://docs.example.atlassian.net", "user@example.com", "secret",
        "12345", transport=httpx.MockTransport(handler),
    )
    created = await adapter.create_report(report())
    assert created == {
        "provider": "confluence", "report_id": "987",
        "title": "Incident report: API outage <severity-1>",
        "url": "https://docs.example.atlassian.net/wiki/spaces/OPS/pages/987",
    }
    reference = await adapter.get_report("987")
    assert reference.provider == "confluence"
    assert reference.report_id == "987"
    assert requests[0].headers["Authorization"].startswith("Basic ")
    await adapter.aclose()


async def test_confluence_distinguishes_missing_report_from_outage():
    def handler(request):
        return httpx.Response(404 if request.url.path.endswith("/404") else 503)

    adapter = ConfluenceIncidentReportAdapter(
        "https://docs.example.atlassian.net", "user@example.com", "secret",
        "12345", transport=httpx.MockTransport(handler),
    )
    assert await adapter.get_report("404") is None
    assert await adapter.get_report("not-a-page-id") is None
    with pytest.raises(ExternalServiceError):
        await adapter.get_report("503")
    await adapter.aclose()
