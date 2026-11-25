"""Read-only incident queries and startup state restoration."""

import logging
from datetime import datetime

from domain.incident.aggregate import Incident, IncidentGroup
from domain.incident.ports import IncidentStatePort

logger = logging.getLogger(__name__)


class GetIncident:
    def __init__(self, incident: Incident) -> None:
        self._incident = incident

    def execute(self) -> dict:
        group = self._incident.group
        return {
            "active": self._incident.is_active,
            "title": self._incident.title if self._incident.is_active else None,
            "channel_name": group.channel_name if self._incident.is_active and group else None,
            "channel_url": group.channel_url if self._incident.is_active and group else None,
            "started_at": (
                self._incident.started_at.isoformat()
                if self._incident.is_active and self._incident.started_at else None
            ),
        }


class RestoreIncident:
    def __init__(self, incident: Incident, state: IncidentStatePort) -> None:
        self._incident = incident
        self._state = state

    def execute(self) -> bool:
        saved = self._state.load()
        if not saved:
            return False
        try:
            self._incident.restore(
                title=saved["title"],
                group=IncidentGroup(**saved["group"]),
                started_at=datetime.fromisoformat(saved["started_at"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            # A damaged state file must not make the whole service unavailable.
            logger.error("Ignoring invalid persisted incident state: %s", exc)
            return False
        logger.info("Restored active incident %s", self._incident.title)
        return True
