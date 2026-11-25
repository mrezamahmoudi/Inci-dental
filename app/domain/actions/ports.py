"""Provider-neutral action-item port."""

from abc import ABC, abstractmethod

from domain.reporting.ports import ReportReference


class ActionItemPort(ABC):
    @abstractmethod
    async def create_action(
        self, description: str, assignee: str, priority: str,
        report: ReportReference, title: str,
    ) -> dict:
        """Create, assign, prioritize, and link an action in the configured tracker."""
