import pytest

from application.reporting.commands import IntegrationDisabledError
from infrastructure.providers import ProviderRegistry


class Provider:
    async def create_report(self, report):
        return {"provider": "gitlab"}

    async def get_report(self, report_id):
        return report_id

    async def create_action(self, **kwargs):
        return kwargs

    async def aclose(self):
        pass


def test_default_and_per_request_provider_selection():
    registry = ProviderRegistry(
        {"confluence": Provider(), "gitlab": Provider()}, {"gitlab": Provider()},
        "confluence", "gitlab",
    )
    assert registry.report_provider() is registry.report_provider("confluence")
    assert registry.report_provider("gitlab") is registry.action_provider()


def test_disabled_provider_does_not_require_an_adapter():
    registry = ProviderRegistry({}, {}, "none", "none")
    with pytest.raises(IntegrationDisabledError, match="disabled"):
        registry.report_provider()
    with pytest.raises(IntegrationDisabledError, match="Unknown"):
        registry.action_provider("jira")
