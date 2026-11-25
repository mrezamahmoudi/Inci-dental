import json

import httpx
import pytest

from domain.reporting.ports import ReportReference
from infrastructure.actions.jira_adapter import JiraActionItemAdapter


@pytest.mark.parametrize("cloud", [True, False])
async def test_jira_creates_assigned_prioritized_issue_and_remote_link(cloud):
    requests = []

    def handler(request):
        requests.append(request)
        payload = json.loads(request.content)
        if request.url.path == "/rest/api/2/issue":
            fields = payload["fields"]
            assert fields["project"] == {"key": "INC"}
            assert fields["priority"] == {"name": "High"}
            assert fields["assignee"] == {
                "accountId" if cloud else "name": "oncall-user",
            }
            assert (fields["description"]["type"] == "doc") if cloud else isinstance(fields["description"], str)
            return httpx.Response(201, json={"id": "10042", "key": "INC-42"})
        assert request.url.path == "/rest/api/2/issue/INC-42/remotelink"
        assert payload["object"]["url"] == "https://docs.example/wiki/pages/987"
        assert payload["relationship"] == "relates to"
        return httpx.Response(201, json={"id": 51})

    adapter = JiraActionItemAdapter(
        "https://jira.example", "secret", "INC", cloud=cloud,
        email="user@example.com" if cloud else None,
        transport=httpx.MockTransport(handler),
    )
    result = await adapter.create_action(
        "Add saturation alerts", "oncall-user", "High",
        ReportReference("gitlab", "incident-report", "https://docs.example/wiki/pages/987"),
        "Add alerts",
    )
    assert result["issue_key"] == "INC-42"
    assert result["url"] == "https://jira.example/browse/INC-42"
    assert result["remote_link_id"] == "51"
    assert len(requests) == 2
    expected_scheme = "Basic" if cloud else "Bearer"
    assert all(request.headers["Authorization"].startswith(expected_scheme) for request in requests)
    await adapter.aclose()
