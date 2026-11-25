import pytest

from HttpHandler.api import Api, load_settings
from infrastructure.actions.jira_adapter import JiraActionItemAdapter
from infrastructure.gitlab_adapter import GitLabAdapter


def base_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("INCIDENT_API_KEY", "secret")
    monkeypatch.setenv("MATTERMOST_URL", "https://chat.example")
    monkeypatch.setenv("MATTERMOST_API_TOKEN", "chat-token")
    monkeypatch.setenv("MATTERMOST_TEAM_ID", "team-id")
    monkeypatch.setenv("INCIDENT_STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setenv("REPORT_PROVIDER", "none")
    monkeypatch.setenv("ACTION_PROVIDER", "none")


def test_disabled_providers_do_not_require_their_credentials(monkeypatch, tmp_path):
    base_environment(monkeypatch, tmp_path)
    for name in ["CONFLUENCE_URL", "JIRA_URL", "GITLAB_URL", "JIRA_API_TOKEN", "GITLAB_TOKEN"]:
        monkeypatch.delenv(name, raising=False)
    api = Api()
    with pytest.raises(Exception, match="disabled"):
        api.providers.report_provider()
    with pytest.raises(Exception, match="disabled"):
        api.providers.action_provider()


def test_private_jira_is_the_default(monkeypatch, tmp_path):
    base_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("ACTION_PROVIDER", "jira")
    monkeypatch.setenv("JIRA_URL", "https://jira.internal.example")
    monkeypatch.setenv("JIRA_API_TOKEN", "token")
    monkeypatch.setenv("JIRA_PROJECT_KEY", "INC")
    monkeypatch.delenv("JIRA_CLOUD", raising=False)
    api = Api()
    assert api.providers.action_provider()._cloud is False


def test_gitlab_only_wiring_does_not_build_atlassian_adapters(monkeypatch, tmp_path):
    base_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("REPORT_PROVIDER", "gitlab")
    monkeypatch.setenv("ACTION_PROVIDER", "gitlab")
    monkeypatch.setenv("GITLAB_URL", "https://gitlab.internal.example")
    monkeypatch.setenv("GITLAB_TOKEN", "token")
    monkeypatch.setenv("GITLAB_PROJECT_ID", "operations/sre")
    for name in ["JIRA_URL", "JIRA_API_TOKEN", "CONFLUENCE_URL", "CONFLUENCE_API_TOKEN"]:
        monkeypatch.delenv(name, raising=False)
    api = Api()
    assert api.providers.report_provider() is api.providers.action_provider()
    assert isinstance(api.providers.report_provider(), GitLabAdapter)


def test_selected_provider_validates_only_its_configuration(monkeypatch, tmp_path):
    base_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("REPORT_PROVIDER", "confluence")
    with pytest.raises(ValueError, match="CONFLUENCE_URL"):
        Api()
