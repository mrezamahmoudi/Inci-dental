import json
from datetime import datetime, timezone

import httpx
import pytest

from infrastructure.incident.mattermost_adapter import MattermostError, MattermostIncidentAdapter


@pytest.fixture
def requests_seen():
    return []


@pytest.fixture
def adapter(requests_seen):
    def handler(request: httpx.Request) -> httpx.Response:
        requests_seen.append(request)
        if request.method == "GET" and request.url.path == "/api/v4/teams/team-id":
            return httpx.Response(200, json={"id": "team-id", "name": "engineering"})
        if request.method == "POST" and request.url.path == "/api/v4/channels":
            payload = json.loads(request.content)
            assert payload["team_id"] == "team-id"
            assert payload["type"] == "P"
            return httpx.Response(201, json={"id": "channel-id", "name": payload["name"]})
        if request.url.path == "/api/v4/users/email/person%40example.com":
            return httpx.Response(200, json={"id": "user-id"})
        if request.url.path == "/api/v4/channels/channel-id/members":
            assert json.loads(request.content) == {"user_id": "user-id"}
            return httpx.Response(201, json={})
        if request.url.path == "/api/v4/posts":
            return httpx.Response(201, json={"id": "post-id"})
        return httpx.Response(404, json={"message": "not found"})

    return MattermostIncidentAdapter(
        "https://chat.example.com", "secret-token", "team-id",
        transport=httpx.MockTransport(handler),
    )


async def test_create_group_adds_members_and_posts_to_new_group(adapter, requests_seen):
    group = await adapter.create_group(
        "Database latency!", datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc),
        ["person@example.com"],
    )
    await adapter.send_started(group, "Database latency!", "operator", datetime.now(timezone.utc), None)
    await adapter.send_responder_checklist(group, ["@person"])
    await adapter.send_reminder(group, "Database latency!", datetime.now(timezone.utc))
    await adapter.send_ended(
        group, "Database latency!", "operator",
        datetime.now(timezone.utc), datetime.now(timezone.utc),
    )
    await adapter.aclose()

    assert group.channel_id == "channel-id"
    assert group.channel_url == "https://chat.example.com/engineering/channels/" + group.channel_name
    assert group.channel_name.startswith("incident-20261125-120000")
    assert len([r for r in requests_seen if r.url.path == "/api/v4/posts"]) == 4
    assert all(r.headers["Authorization"] == "Bearer secret-token" for r in requests_seen)


async def test_api_error_is_sanitized():
    def failure(request):
        return httpx.Response(500, text="upstream secret details")

    adapter = MattermostIncidentAdapter(
        "https://chat.example.com", "secret-token", "team-id",
        transport=httpx.MockTransport(failure),
    )
    with pytest.raises(MattermostError) as error:
        await adapter.create_group(
            "Outage", datetime.now(timezone.utc), [],
        )
    assert "secret-token" not in str(error.value)
    assert "upstream secret details" not in str(error.value)
    assert "HTTP 500" in str(error.value)
    await adapter.aclose()
