from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.auth import ApiKeyAuthenticator
from api.routers.incident import router
from domain.incident.aggregate import Incident, IncidentGroup


class StubStart:
    async def execute(self, title, username):
        group = IncidentGroup("id", "incident-1", "https://chat.example/incident-1")
        return {"active": True, "title": title, "channel_name": group.channel_name, "channel_url": group.channel_url}


class StubEnd:
    async def execute(self, username):
        return {"active": False}


def client():
    app = FastAPI()
    app.state.incident = Incident()
    app.state.start_incident = StubStart()
    app.state.end_incident = StubEnd()
    app.state.auth = ApiKeyAuthenticator("test-key")
    app.state.record_started = lambda actor: None
    app.state.record_ended = lambda actor: None
    app.include_router(router)
    return TestClient(app)


def test_mutations_require_api_key_and_input_validation():
    api = client()
    assert api.post("/api/v1/incidents", json={"title": "Outage"}).status_code == 401
    assert api.post(
        "/api/v1/incidents", json={"title": " "},
        headers={"Authorization": "Bearer test-key"},
    ).status_code == 422
    assert api.get("/api/v1/incidents/current").status_code == 200


def test_start_and_end_use_authenticated_actor():
    api = client()
    headers = {"Authorization": "Bearer test-key", "X-Actor": "release-bot"}
    started = api.post("/api/v1/incidents", json={"title": "Outage"}, headers=headers)
    assert started.status_code == 201
    assert started.json()["channel_name"] == "incident-1"
    ended = api.post("/api/v1/incidents/current/end", headers=headers)
    assert ended.status_code == 200
    assert ended.json()["active"] is False
