"""Abstract external capabilities required by the incident application."""

from abc import ABC, abstractmethod
from datetime import datetime

from domain.incident.aggregate import IncidentGroup


class IncidentGroupPort(ABC):
    @abstractmethod
    async def create_group(
        self, title: str, started_at: datetime, members: list[str]
    ) -> IncidentGroup:
        """Create a uniquely named incident group and add initial members."""

    @abstractmethod
    async def send_started(
        self, group: IncidentGroup, title: str, started_by: str,
        started_at: datetime, oncall_url: str | None,
    ) -> None:
        """Send the incident-start announcement to the new group."""

    @abstractmethod
    async def send_responder_checklist(
        self, group: IncidentGroup, responders: list[str]
    ) -> None:
        """Ask configured responders to review their services."""

    @abstractmethod
    async def send_ended(
        self, group: IncidentGroup, title: str, ended_by: str,
        started_at: datetime, ended_at: datetime,
    ) -> None:
        """Announce the end and elapsed duration in the incident group."""

    @abstractmethod
    async def send_reminder(
        self, group: IncidentGroup, title: str, started_at: datetime,
    ) -> None:
        """Send an active-incident reminder to its group."""


class IncidentStatePort(ABC):
    @abstractmethod
    def save_active(
        self, title: str, group: IncidentGroup, started_at: datetime
    ) -> None:
        """Durably save the complete active incident."""

    @abstractmethod
    def save_inactive(self) -> None:
        """Durably mark the incident inactive."""

    @abstractmethod
    def load(self) -> dict | None:
        """Return a previously active incident, or None when inactive."""
