"""Small async background reminder task; no chat membership synchronization."""

import asyncio
import logging

from domain.incident.aggregate import Incident
from domain.incident.ports import IncidentGroupPort

logger = logging.getLogger(__name__)


async def run_incident_reminders(
    incident: Incident, groups: IncidentGroupPort, interval_seconds: int
) -> None:
    while True:
        await asyncio.sleep(interval_seconds)
        if not incident.is_active:
            continue
        try:
            await groups.send_reminder(
                incident.group, incident.title, incident.started_at,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Incident reminder failed: %s", exc)
