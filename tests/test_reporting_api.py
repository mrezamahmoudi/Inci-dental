from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.auth import ApiKeyAuthenticator
from api.routers.reporting import router


class CreateReport:
    async def execute(self, report):
        assert report.created_by == "oncall-bot"
        return {"provider": "confluence", "report_id": "987", "title": report.title, "url": "https://docs.example/987"}


class CreateAction:
    async def execute(self, **kwargs):
        return {
            "issue_id": "10042", "issue_key": "INC-42",
            "url": "https://jira.example/browse/INC-42", **kwargs,
            "remote_link_id": "51",
        }


def client():
    app = FastAPI()
    app.state.auth = ApiKeyAuthenticator("test-key")
    app.state.create_incident_report = CreateReport()
    app.state.create_action_item = CreateAction()
    app.include_router(router)
    return TestClient(app)


def report_payload():
    return {
        "title": "API outage", "summary": "API was unavailable.",
        "impact": "Users could not sign in.", "root_cause": "Failed failover.",
        "timeline": "12:00 detected; 12:10 mitigated.", "resolution": "Restored primary.",
    }


def action_payload():
    return {
        "description": "Add saturation alerts", "assignee": "jira-account-id",
        "priority": "High", "related_report_id": "987", "title": "Add alerts",
    }


def test_report_and_action_require_authentication():
    api = client()
    assert api.post("/api/v1/incident-reports", json=report_payload()).status_code == 401
    assert api.post("/api/v1/actions", json=action_payload()).status_code == 401


def test_create_report_and_assigned_action():
    api = client()
    headers = {"Authorization": "Bearer test-key", "X-Actor": "oncall-bot"}
    report = api.post("/api/v1/incident-reports", json=report_payload(), headers=headers)
    assert report.status_code == 201
    assert report.json()["report_id"] == "987"

    action = api.post("/api/v1/actions", json=action_payload(), headers=headers)
    assert action.status_code == 201
    assert action.json()["issue_key"] == "INC-42"
    assert action.json()["assignee"] == "jira-account-id"
    assert action.json()["related_report_id"] == "987"


def test_action_requires_valid_report_id_and_fields():
    api = client()
    headers = {"Authorization": "Bearer test-key"}
    payload = action_payload()
    payload["related_report_id"] = " "
    assert api.post("/api/v1/actions", json=payload, headers=headers).status_code == 422
    payload = action_payload()
    del payload["priority"]
    assert api.post("/api/v1/actions", json=payload, headers=headers).status_code == 422
