"""Pure incident-report value object and creation contract."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class IncidentReport:
    title: str
    summary: str
    impact: str
    root_cause: str
    timeline: str
    resolution: str
    created_by: str
    created_at: datetime


@dataclass(frozen=True)
class ReportReference:
    """Provider-neutral pointer used to link actions to any report backend."""

    provider: str
    report_id: str
    url: str


class IncidentReportPort(ABC):
    @abstractmethod
    async def create_report(self, report: IncidentReport) -> dict:
        """Create a report and return its provider, external id, title, and URL."""

    @abstractmethod
    async def get_report(self, report_id: str) -> ReportReference | None:
        """Resolve and verify a report, or return None when it does not exist."""
