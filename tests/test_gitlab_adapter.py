from urllib.parse import parse_qs

import httpx

from domain.reporting.ports import IncidentReport, ReportReference
from infrastructure.gitlab_adapter import GitLabAdapter
from tests.test_confluence_adapter import report as make_report


async def test_private_gitlab_wiki_report_and_assigned_issue():
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path.endswith("/wikis") and request.method == "POST":
            return httpx.Response(201, json={"title": "Incident report: API outage", "slug": "incident-123"})
        if request.url.path.endswith("/wikis/incident-123"):
            return httpx.Response(200, json={"slug": "incident-123"})
        if request.url.path == "/api/v4/users":
            assert request.url.params["username"] == "oncall-user"
            return httpx.Response(200, json=[{"id": 42, "username": "oncall-user"}])
        if request.url.path.endswith("/issues"):
            body = parse_qs(request.content.decode())
            assert body["assignee_ids[]"] == ["42"]
            assert "priority::High" in body["labels"][0]
            assert "https://gitlab.example/operations/sre/-/wikis/incident-123" in body["description"][0]
            return httpx.Response(201, json={"iid": 51, "web_url": "https://gitlab.example/operations/sre/-/issues/51"})
        return httpx.Response(404)

    adapter = GitLabAdapter(
        "https://gitlab.example", "private-token", "operations/sre",
        transport=httpx.MockTransport(handler),
    )
    created = await adapter.create_report(make_report())
    assert created["provider"] == "gitlab"
    assert created["report_id"] == "incident-123"
    reference = await adapter.get_report("incident-123")
    assert reference.url.endswith("/operations/sre/-/wikis/incident-123")
    result = await adapter.create_action(
        "Add saturation alert", "oncall-user", "High", reference, "Add alert",
    )
    assert result["issue_key"] == "operations/sre#51"
    assert result["related_report_id"] == "incident-123"
    assert all(request.headers["PRIVATE-TOKEN"] == "private-token" for request in requests)
    await adapter.aclose()
