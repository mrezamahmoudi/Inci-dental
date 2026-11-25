import pytest

from application.actions.commands import CreateActionItem
from domain.reporting.ports import ReportReference
from infrastructure.http_client import ExternalServiceError


class Reports:
    def __init__(self, exists=True):
        self.exists = exists

    async def get_report(self, report_id):
        if not self.exists:
            return None
        return ReportReference("confluence", report_id, "https://docs.example/123")

    async def create_report(self, report):
        return {"report_id": "123", "title": report.title, "url": "https://docs.example/123"}


class Actions:
    def __init__(self):
        self.arguments = None

    async def create_action(self, **kwargs):
        self.arguments = kwargs
        return {"issue_key": "INC-42", "related_report_id": kwargs["report"].report_id}


async def test_action_is_assigned_to_supplied_oncall_and_linked_to_report():
    actions = Actions()
    result = await CreateActionItem(actions, Reports()).execute(
        description="Add a saturation alert", assignee="jira-account-id",
        priority="High", related_report_id="123", title="Add database alert",
    )
    assert result["issue_key"] == "INC-42"
    assert actions.arguments == {
        "description": "Add a saturation alert", "assignee": "jira-account-id",
        "priority": "High", "report": ReportReference(
            "confluence", "123", "https://docs.example/123",
        ), "title": "Add database alert",
    }


async def test_action_rejects_missing_report_without_creating_jira_issue():
    actions = Actions()
    with pytest.raises(ValueError, match="does not exist"):
        await CreateActionItem(actions, Reports(exists=False)).execute(
            "Add alert", "oncall", "High", "404", "",
        )
    assert actions.arguments is None


async def test_action_does_not_hide_report_lookup_outage():
    class BrokenReports(Reports):
        async def get_report(self, report_id):
            raise ExternalServiceError("Confluence", "unavailable", 503)

    with pytest.raises(ExternalServiceError):
        await CreateActionItem(Actions(), BrokenReports()).execute(
            "Add alert", "oncall", "High", "123", "",
        )
