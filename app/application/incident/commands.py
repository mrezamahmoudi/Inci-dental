"""Write operations orchestrating the incident aggregate and its ports."""

import asyncio
import logging

from domain.incident.aggregate import (
    Incident, IncidentAlreadyActiveError, NoActiveIncidentError, utc_now,
)
from domain.incident.ports import IncidentGroupPort, IncidentStatePort

logger = logging.getLogger(__name__)


class IncidentOperationError(Exception):
    """Raised when an external dependency prevents an incident operation."""


class StartIncident:
    def __init__(
        self, incident: Incident, groups: IncidentGroupPort,
        state: IncidentStatePort, initial_members: list[str],
        responders: list[str], oncall_url: str | None = None,
    ) -> None:
        self._incident = incident
        self._groups = groups
        self._state = state
        self._initial_members = initial_members
        self._responders = responders
        self._oncall_url = oncall_url
        self._start_lock = asyncio.Lock()

    async def execute(self, title: str, started_by: str) -> dict:
        # Hold the lock across channel creation so concurrent requests cannot
        # both pass the inactive check and create two incident groups.
        async with self._start_lock:
            return await self._execute(title, started_by)

    async def _execute(self, title: str, started_by: str) -> dict:
        # Check before creating anything: a rejected retry must not leak a group.
        if self._incident.is_active:
            raise IncidentAlreadyActiveError("An incident is already active.")

        title = title.strip()
        if not title:
            raise ValueError("Incident title cannot be empty.")
        started_at = utc_now()
        group = await self._groups.create_group(
            title=title, started_at=started_at, members=self._initial_members,
        )
        # External creation succeeded. From this point retain the group in the
        # aggregate so a notification failure never strands an unknown group.
        self._incident.start(title, group, started_at)
        try:
            self._state.save_active(title, group, started_at)
        except Exception as exc:
            self._incident.end()
            raise IncidentOperationError(
                f"Incident group {group.channel_name} was created, but state could "
                "not be saved. Resolve storage before starting another incident."
            ) from exc

        logger.info("Incident started in group %s by %s", group.channel_name, started_by)
        # The group already exists and state is durable. A temporary messaging
        # outage must not make the operator create a second incident group.
        await self._notify_start(group, title, started_by, started_at)
        return {
            "active": True,
            "title": title,
            "channel_name": group.channel_name,
            "channel_url": group.channel_url,
            "started_at": started_at.isoformat(),
        }

    async def _notify_start(self, group, title, started_by, started_at) -> None:
        results = await asyncio.gather(
            self._groups.send_started(
                group, title, started_by, started_at, self._oncall_url,
            ),
            self._groups.send_responder_checklist(group, self._responders),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):
                logger.error("Incident start notification failed: %s", result)


class EndIncident:
    def __init__(
        self, incident: Incident, groups: IncidentGroupPort, state: IncidentStatePort
    ) -> None:
        self._incident = incident
        self._groups = groups
        self._state = state

    async def execute(self, ended_by: str) -> dict:
        if not self._incident.is_active:
            raise NoActiveIncidentError("No incident is active.")

        title = self._incident.title
        group = self._incident.group
        started_at = self._incident.started_at
        ended_at = utc_now()
        # Send while the active incident is still durable. If delivery fails,
        # the operator can safely retry instead of losing the group reference.
        try:
            await self._groups.send_ended(
                group, title, ended_by, started_at, ended_at,
            )
        except Exception as exc:
            raise IncidentOperationError(
                "Incident is still active because its end notification failed. Retry the request."
            ) from exc

        self._state.save_inactive()
        self._incident.end()
        logger.info("Incident ended in group %s by %s", group.channel_name, ended_by)
        return {
            "active": False,
            "title": title,
            "channel_name": group.channel_name,
            "channel_url": group.channel_url,
            "ended_at": ended_at.isoformat(),
        }
