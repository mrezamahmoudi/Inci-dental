"""Route operations to the provider selected by configuration or request."""

from application.reporting.commands import IntegrationDisabledError
from domain.actions.ports import ActionItemPort
from domain.reporting.ports import IncidentReportPort


class ProviderRegistry(IncidentReportPort, ActionItemPort):
    """One place for provider choice; domain and API models stay provider-neutral."""

    def __init__(
        self, report_providers: dict[str, IncidentReportPort],
        action_providers: dict[str, ActionItemPort],
        default_report_provider: str, default_action_provider: str,
    ) -> None:
        self._reports = report_providers
        self._actions = action_providers
        self._default_report = default_report_provider
        self._default_action = default_action_provider

    def report_provider(self, name: str | None = None) -> IncidentReportPort:
        return self._select(
            self._reports, name or self._default_report, "incident reporting",
        )

    def action_provider(self, name: str | None = None) -> ActionItemPort:
        return self._select(
            self._actions, name or self._default_action, "action tracking",
        )

    async def create_report(self, report):
        return await self.report_provider().create_report(report)

    async def get_report(self, report_id: str):
        return await self.report_provider().get_report(report_id)

    async def create_action(self, **kwargs):
        return await self.action_provider().create_action(**kwargs)

    @staticmethod
    def _select(providers: dict, name: str, capability: str):
        if name == "none":
            raise IntegrationDisabledError(f"The {capability} integration is disabled.")
        try:
            return providers[name]
        except KeyError as exc:
            supported = ", ".join(sorted([*providers, "none"]))
            raise IntegrationDisabledError(
                f"Unknown {capability} provider '{name}'. Choose one of: {supported}."
            ) from exc

    async def aclose(self) -> None:
        # Close each configured adapter exactly once, even if used for both roles.
        clients = {
            id(adapter): adapter
            for adapter in [*self._reports.values(), *self._actions.values()]
        }
        for adapter in clients.values():
            await adapter.aclose()
