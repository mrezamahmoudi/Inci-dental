"""Composition root: provider selection, adapters, commands, and lifecycle."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest

from api.auth import ApiKeyAuthenticator
from api.routers.incident import router as incident_router
from api.routers.reporting import router as reporting_router
from application.actions.commands import CreateActionItem
from application.incident.commands import EndIncident, StartIncident
from application.incident.queries import RestoreIncident
from application.incident.tasks import run_incident_reminders
from application.reporting.commands import CreateIncidentReport
from domain.incident.aggregate import Incident
from infrastructure.actions.jira_adapter import JiraActionItemAdapter
from infrastructure.gitlab_adapter import GitLabAdapter
from infrastructure.incident.mattermost_adapter import MattermostIncidentAdapter
from infrastructure.incident.state_adapter import FileIncidentStateAdapter
from infrastructure.providers import ProviderRegistry
from infrastructure.reporting.confluence_adapter import ConfluenceIncidentReportAdapter


@dataclass(frozen=True)
class Settings:
    """Provider-independent settings shared by incident coordination."""

    incident_api_key: str
    incident_channel_prefix: str
    private_channels: bool
    initial_members: list[str]
    responders: list[str]
    oncall_url: str | None
    state_file: str
    reminder_interval_seconds: int
    chat_provider: str
    report_provider: str
    action_provider: str


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Required environment variable {name} is not set.")
    return value


def _list(name: str) -> list[str]:
    return list(dict.fromkeys(
        item.strip() for item in os.getenv(name, "").split(",") if item.strip()
    ))


def load_settings() -> Settings:
    interval = int(os.getenv("INCIDENT_REMINDER_INTERVAL_SECONDS", "1800"))
    if interval < 1:
        raise ValueError("INCIDENT_REMINDER_INTERVAL_SECONDS must be positive.")
    return Settings(
        incident_api_key=_required("INCIDENT_API_KEY"),
        incident_channel_prefix=os.getenv("INCIDENT_CHANNEL_PREFIX", "incident"),
        private_channels=os.getenv("MATTERMOST_PRIVATE_CHANNELS", "true").lower() == "true",
        initial_members=_list("INCIDENT_INITIAL_MEMBERS"),
        responders=_list("INCIDENT_RESPONDERS"),
        oncall_url=os.getenv("ONCALL_URL", "").strip() or None,
        state_file=os.getenv("INCIDENT_STATE_FILE", "/data/incident-state.json"),
        reminder_interval_seconds=interval,
        chat_provider=os.getenv("CHAT_PROVIDER", "mattermost").strip().lower(),
        report_provider=os.getenv("REPORT_PROVIDER", "none").strip().lower(),
        action_provider=os.getenv("ACTION_PROVIDER", "none").strip().lower(),
    )


class Api:
    """All dependencies are constructed once, only for selected providers."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()
        self.incident = Incident()
        self.incident_state = FileIncidentStateAdapter(self.settings.state_file)
        self.chat = self._build_chat_provider()
        self.providers = self._build_providers()
        RestoreIncident(self.incident, self.incident_state).execute()
        self.start_incident = StartIncident(
            incident=self.incident, groups=self.chat, state=self.incident_state,
            initial_members=self.settings.initial_members,
            responders=self.settings.responders, oncall_url=self.settings.oncall_url,
        )
        self.end_incident = EndIncident(self.incident, self.chat, self.incident_state)
        self.create_incident_report = CreateIncidentReport(self.providers)
        self.create_action_item = CreateActionItem(self.providers, self.providers)
        self._reminder_task: asyncio.Task | None = None

        self.started_total = Counter(
            "incidental_incidents_started_total", "Incidents started", ["actor"],
        )
        self.ended_total = Counter(
            "incidental_incidents_ended_total", "Incidents ended", ["actor"],
        )
        self.active_gauge = Gauge(
            "incidental_incident_active", "Whether an incident is currently active",
        )
        self.active_gauge.set(int(self.incident.is_active))

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            self._reminder_task = asyncio.create_task(
                run_incident_reminders(
                    self.incident, self.chat, self.settings.reminder_interval_seconds,
                )
            )
            try:
                yield
            finally:
                self._reminder_task.cancel()
                try:
                    await self._reminder_task
                except asyncio.CancelledError:
                    pass
                await self.chat.aclose()
                await self.providers.aclose()

        self.app = FastAPI(
            title="Inci-dental",
            description="Provider-neutral incident coordination, reports, and actions.",
            version="0.2.0", lifespan=lifespan,
        )
        self.app.state.incident = self.incident
        self.app.state.start_incident = self.start_incident
        self.app.state.end_incident = self.end_incident
        self.app.state.create_incident_report = self.create_incident_report
        self.app.state.create_action_item = self.create_action_item
        self.app.state.auth = ApiKeyAuthenticator(self.settings.incident_api_key)
        self.app.state.record_started = self._record_started
        self.app.state.record_ended = self._record_ended
        self.app.include_router(incident_router)
        self.app.include_router(reporting_router)
        self.app.add_api_route("/healthz", self.health, methods=["GET"], include_in_schema=False)
        self.app.add_api_route("/metrics", self.metrics, methods=["GET"], include_in_schema=False)

    def _build_chat_provider(self):
        if self.settings.chat_provider != "mattermost":
            raise ValueError("CHAT_PROVIDER currently supports only 'mattermost'.")
        return MattermostIncidentAdapter(
            server_url=_required("MATTERMOST_URL"),
            api_token=_required("MATTERMOST_API_TOKEN"),
            team_id=_required("MATTERMOST_TEAM_ID"),
            channel_prefix=self.settings.incident_channel_prefix,
            private_channels=self.settings.private_channels,
        )

    def _build_providers(self) -> ProviderRegistry:
        reports, actions = {}, {}
        selected = {self.settings.report_provider, self.settings.action_provider}

        if "confluence" in selected:
            confluence = ConfluenceIncidentReportAdapter(
                base_url=_required("CONFLUENCE_URL"),
                email=_required("CONFLUENCE_EMAIL"),
                api_token=_required("CONFLUENCE_API_TOKEN"),
                space_id=_required("CONFLUENCE_SPACE_ID"),
                parent_page_id=os.getenv("CONFLUENCE_PARENT_PAGE_ID", "").strip() or None,
            )
            reports["confluence"] = confluence
        if "gitlab" in selected:
            gitlab = GitLabAdapter(
                base_url=_required("GITLAB_URL"), token=_required("GITLAB_TOKEN"),
                project_id=_required("GITLAB_PROJECT_ID"),
            )
            reports["gitlab"] = gitlab
            actions["gitlab"] = gitlab
        if "jira" in selected:
            cloud = os.getenv("JIRA_CLOUD", "false").lower() == "true"
            email = os.getenv("JIRA_EMAIL", "").strip() or None
            if cloud and not email:
                raise ValueError("JIRA_EMAIL is required when JIRA_CLOUD=true.")
            actions["jira"] = JiraActionItemAdapter(
                base_url=_required("JIRA_URL"), api_token=_required("JIRA_API_TOKEN"),
                project_key=_required("JIRA_PROJECT_KEY"),
                issue_type=os.getenv("JIRA_ISSUE_TYPE", "Task").strip(),
                email=email, cloud=cloud,
            )
        return ProviderRegistry(
            report_providers=reports, action_providers=actions,
            default_report_provider=self.settings.report_provider,
            default_action_provider=self.settings.action_provider,
        )

    def _record_started(self, actor: str) -> None:
        self.started_total.labels(actor=actor).inc()
        self.active_gauge.set(1)

    def _record_ended(self, actor: str) -> None:
        self.ended_total.labels(actor=actor).inc()
        self.active_gauge.set(0)

    @staticmethod
    def health() -> dict:
        return {"status": "ok"}

    @staticmethod
    def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def create_app() -> FastAPI:
    """Uvicorn entrypoint: PYTHONPATH=app uvicorn HttpHandler.api:create_app --factory."""
    return Api().app
