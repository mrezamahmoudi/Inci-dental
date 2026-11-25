from datetime import datetime, timezone

import pytest

from domain.incident.aggregate import (
    Incident, IncidentAlreadyActiveError, IncidentGroup, NoActiveIncidentError,
)


def test_incident_lifecycle_and_invariants():
    incident = Incident()
    group = IncidentGroup("channel-id", "incident-1", "https://chat.example/incident-1")
    started_at = datetime.now(timezone.utc)

    assert not incident.is_active
    with pytest.raises(NoActiveIncidentError):
        incident.end()

    incident.start("Database unavailable", group, started_at)
    assert incident.is_active
    assert incident.group == group
    with pytest.raises(IncidentAlreadyActiveError):
        incident.start("Another incident", group, started_at)

    incident.end()
    assert not incident.is_active


def test_incident_requires_title_and_aware_start_time():
    incident = Incident()
    group = IncidentGroup("id", "name", "https://chat.example/name")
    with pytest.raises(ValueError):
        incident.start(" ", group, datetime.now(timezone.utc))
    with pytest.raises(ValueError):
        incident.start("Outage", group, datetime.now())
