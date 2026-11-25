import asyncio

import pytest

from application.incident.commands import EndIncident, IncidentOperationError, StartIncident
from application.incident.queries import RestoreIncident
from domain.incident.aggregate import Incident, IncidentAlreadyActiveError, IncidentGroup
from infrastructure.incident.state_adapter import FileIncidentStateAdapter


class FakeGroups:
    def __init__(self):
        self.created = []
        self.messages = []
        self.fail_start = False
        self.fail_end = False

    async def create_group(self, title, started_at, members):
        await asyncio.sleep(0)
        self.created.append((title, members))
        return IncidentGroup("id-1", "incident-1", "https://chat.example/incident-1")

    async def send_started(self, group, title, started_by, started_at, oncall_url):
        if self.fail_start:
            raise RuntimeError("chat unavailable")
        self.messages.append(("started", group.channel_id))

    async def send_responder_checklist(self, group, responders):
        self.messages.append(("responders", responders))

    async def send_ended(self, group, title, ended_by, started_at, ended_at):
        if self.fail_end:
            raise RuntimeError("chat unavailable")
        self.messages.append(("ended", group.channel_id))

    async def send_reminder(self, group, title, started_at):
        self.messages.append(("reminder", group.channel_id))


def make_start(incident, groups, state):
    return StartIncident(
        incident, groups, state, ["person@example.com"], ["@person"], None,
    )


async def test_start_creates_group_before_messages_and_persists_it(tmp_path):
    incident, groups = Incident(), FakeGroups()
    state = FileIncidentStateAdapter(str(tmp_path / "incident.json"))
    result = await make_start(incident, groups, state).execute("API outage", "operator")

    assert groups.created == [("API outage", ["person@example.com"])]
    assert result["channel_name"] == "incident-1"
    assert incident.is_active
    restored = Incident()
    assert RestoreIncident(restored, state).execute()
    assert restored.group == incident.group
    assert restored.title == "API outage"

    with pytest.raises(IncidentAlreadyActiveError):
        await make_start(incident, groups, state).execute("Duplicate", "operator")
    assert len(groups.created) == 1


async def test_concurrent_starts_create_only_one_group(tmp_path):
    incident, groups = Incident(), FakeGroups()
    state = FileIncidentStateAdapter(str(tmp_path / "incident.json"))
    command = make_start(incident, groups, state)
    results = await asyncio.gather(
        command.execute("Outage", "operator"),
        command.execute("Duplicate", "operator"),
        return_exceptions=True,
    )

    assert len(groups.created) == 1
    assert sum(isinstance(result, IncidentAlreadyActiveError) for result in results) == 1


async def test_start_notification_failure_keeps_recoverable_active_incident(tmp_path):
    incident, groups = Incident(), FakeGroups()
    groups.fail_start = True
    state = FileIncidentStateAdapter(str(tmp_path / "incident.json"))
    result = await make_start(incident, groups, state).execute("Outage", "operator")

    assert result["active"] is True
    assert state.load()["group"]["channel_id"] == "id-1"
    assert len(groups.created) == 1


async def test_end_failure_is_retryable_and_success_clears_state(tmp_path):
    incident, groups = Incident(), FakeGroups()
    state = FileIncidentStateAdapter(str(tmp_path / "incident.json"))
    await make_start(incident, groups, state).execute("Outage", "operator")
    end = EndIncident(incident, groups, state)
    groups.fail_end = True

    with pytest.raises(IncidentOperationError):
        await end.execute("operator")
    assert incident.is_active

    groups.fail_end = False
    result = await end.execute("operator")
    assert result["active"] is False
    assert not incident.is_active
    assert state.load() is None


async def test_state_save_failure_does_not_report_success(tmp_path):
    incident, groups = Incident(), FakeGroups()
    blocked_path = tmp_path / "not-a-directory"
    blocked_path.write_text("file")
    state = FileIncidentStateAdapter(str(blocked_path / "incident.json"))

    with pytest.raises(IncidentOperationError, match="incident-1"):
        await make_start(incident, groups, state).execute("Outage", "operator")
    assert not incident.is_active
