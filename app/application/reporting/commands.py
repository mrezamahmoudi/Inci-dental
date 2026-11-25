"""Incident report creation orchestration."""

from domain.reporting.ports import IncidentReport, IncidentReportPort


class IntegrationDisabledError(Exception):
    """Raised when a client selects a disabled or unknown provider."""


class CreateIncidentReport:
    def __init__(self, reports: IncidentReportPort) -> None:
        self._reports = reports

    async def execute(self, report: IncidentReport) -> dict:
        if not report.title.strip():
            raise ValueError("Report title cannot be empty.")
        return await self._reports.create_report(report)
