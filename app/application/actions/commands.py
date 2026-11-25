"""Create an action only after its incident report reference is verified."""

from domain.actions.ports import ActionItemPort
from domain.reporting.ports import IncidentReportPort


class CreateActionItem:
    def __init__(self, actions: ActionItemPort, reports: IncidentReportPort) -> None:
        self._actions = actions
        self._reports = reports

    async def execute(
        self, description: str, assignee: str, priority: str,
        related_report_id: str, title: str, report_provider: str | None = None,
    ) -> dict:
        reports = (
            self._reports.report_provider(report_provider)
            if hasattr(self._reports, "report_provider") else self._reports
        )
        report = await reports.get_report(related_report_id)
        if report is None:
            raise ValueError("The related incident report does not exist.")
        return await self._actions.create_action(
            description=description, assignee=assignee, priority=priority,
            report=report, title=title,
        )
