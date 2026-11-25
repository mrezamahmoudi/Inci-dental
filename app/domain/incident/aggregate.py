"""Pure incident state machine. No external dependencies."""

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class IncidentGroup:
    """A chat group owned by one incident."""

    channel_id: str
    channel_name: str
    channel_url: str


class IncidentAlreadyActiveError(Exception):
    """Raised when a second incident is started while one is active."""


class NoActiveIncidentError(Exception):
    """Raised when an active incident is required."""


class Incident:
    """Aggregate root enforcing one active incident at a time."""

    def __init__(self) -> None:
        self._active = False
        self._title: str | None = None
        self._group: IncidentGroup | None = None
        self._started_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def title(self) -> str | None:
        return self._title

    @property
    def group(self) -> IncidentGroup | None:
        return self._group

    @property
    def started_at(self) -> datetime | None:
        return self._started_at

    def start(self, title: str, group: IncidentGroup, started_at: datetime) -> None:
        if self._active:
            raise IncidentAlreadyActiveError("An incident is already active.")
        if not title.strip():
            raise ValueError("Incident title cannot be empty.")
        if started_at.tzinfo is None:
            raise ValueError("Incident start time must be timezone-aware.")

        self._active = True
        self._title = title.strip()
        self._group = group
        self._started_at = started_at

    def end(self) -> None:
        if not self._active:
            raise NoActiveIncidentError("No incident is active.")
        self._active = False

    def restore(self, title: str, group: IncidentGroup, started_at: datetime) -> None:
        """Restore an active incident without creating external resources."""
        self._active = False
        self.start(title, group, started_at)


def utc_now() -> datetime:
    """Small UTC clock helper kept in the domain for deterministic callers."""
    return datetime.now(timezone.utc)
