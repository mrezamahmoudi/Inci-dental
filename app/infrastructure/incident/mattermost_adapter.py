"""Mattermost adapter implemented directly against the public REST API."""

import asyncio
import logging
import re
from datetime import datetime
from urllib.parse import quote

import httpx

from domain.incident.aggregate import IncidentGroup
from domain.incident.ports import IncidentGroupPort

logger = logging.getLogger(__name__)


class MattermostError(Exception):
    """An expected Mattermost API failure, without credentials in the message."""


class MattermostIncidentAdapter(IncidentGroupPort):
    """Creates one private channel per incident and posts to that channel only."""

    def __init__(
        self, server_url: str, api_token: str, team_id: str,
        channel_prefix: str = "incident", private_channels: bool = True,
        timeout_seconds: float = 15.0, transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._server_url = server_url.rstrip("/")
        self._team_id = team_id
        self._channel_prefix = self._slug(channel_prefix) or "incident"
        self._channel_type = "P" if private_channels else "O"
        self._client = httpx.AsyncClient(
            base_url=f"{self._server_url}/api/v4",
            headers={"Authorization": f"Bearer {api_token}"},
            timeout=httpx.Timeout(timeout_seconds),
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def create_group(
        self, title: str, started_at: datetime, members: list[str]
    ) -> IncidentGroup:
        suffix = self._slug(title)[:30].strip("-") or "incident"
        # Microseconds make channel names unique even for repeated titles.
        name = (
            f"{self._channel_prefix}-{started_at:%Y%m%d-%H%M%S%f}-{suffix}"
        )[:64].rstrip("-")
        display_name = f"Incident: {title.strip()}"[:64]
        team = await self._request(
            "GET", f"/teams/{quote(self._team_id, safe='')}",
        )
        team_name = team.get("name")
        if not team_name:
            raise MattermostError("Mattermost returned an incomplete team response.")
        channel = await self._request(
            "POST", "/channels", json={
                "team_id": self._team_id,
                "name": name,
                "display_name": display_name,
                "type": self._channel_type,
                "purpose": "Incident coordination. Created automatically by Inci-dental.",
            },
        )
        channel_id = channel.get("id")
        channel_name = channel.get("name")
        if not channel_id or not channel_name:
            raise MattermostError("Mattermost returned an incomplete channel response.")

        # Resolve users concurrently, but never reveal the API token in errors.
        resolved = await asyncio.gather(
            *(self._resolve_member(channel_id, email) for email in members)
        )
        failed = [email for email, added in zip(members, resolved) if not added]
        if failed:
            # Do not delete the created channel or silently discard its ID. The
            # caller persists it and can manually add anyone whose lookup failed.
            logger.warning("Could not add initial Mattermost members: %s", ", ".join(failed))

        return IncidentGroup(
            channel_id=channel_id,
            channel_name=channel_name,
            channel_url=(
                f"{self._server_url}/{quote(team_name, safe='')}"
                f"/channels/{quote(channel_name, safe='')}"
            ),
        )

    async def send_started(
        self, group: IncidentGroup, title: str, started_by: str,
        started_at: datetime, oncall_url: str | None,
    ) -> None:
        text = (
            f"## 🚨 Incident started: {title}\n\n"
            f"**Started by:** {started_by}  \n"
            f"**Started at (UTC):** {started_at.isoformat()}  \n"
            "Use this group for all incident coordination and updates."
        )
        if oncall_url:
            text += f"\n\n[Open the on-call schedule]({oncall_url})"
        await self._post(group.channel_id, text, urgent=True)

    async def send_responder_checklist(
        self, group: IncidentGroup, responders: list[str]
    ) -> None:
        people = ", ".join(responders) if responders else "Incident responders"
        await self._post(
            group.channel_id,
            f"### Service review\n{people}: please review your services, "
            "share their current health, and report relevant findings here.",
        )

    async def send_ended(
        self, group: IncidentGroup, title: str, ended_by: str,
        started_at: datetime, ended_at: datetime,
    ) -> None:
        duration = self._format_duration(ended_at - started_at)
        await self._post(
            group.channel_id,
            f"## ✅ Incident ended: {title}\n\n"
            f"**Ended by:** {ended_by}  \n"
            f"**Duration:** {duration}  \n"
            "Continue post-incident review and follow-up in your normal process.",
        )

    async def send_reminder(
        self, group: IncidentGroup, title: str, started_at: datetime,
    ) -> None:
        await self._post(
            group.channel_id,
            f"### Incident still active: {title}\n"
            f"Started at {started_at.isoformat()}. Please share a status update.",
        )

    async def _resolve_member(self, channel_id: str, email: str) -> bool:
        try:
            user = await self._request(
                "GET", f"/users/email/{quote(email.strip(), safe='')}",
            )
            user_id = user.get("id")
            if not user_id:
                return False
            await self._request(
                "POST", f"/channels/{quote(channel_id, safe='')}/members",
                json={"user_id": user_id},
            )
            return True
        except MattermostError as exc:
            logger.warning("Initial member lookup/add failed for %s: %s", email, exc)
            return False

    async def _post(self, channel_id: str, message: str, urgent: bool = False) -> None:
        payload = {"channel_id": channel_id, "message": message}
        if urgent:
            payload["metadata"] = {
                "priority": {"priority": "urgent", "requested_ack": False},
            }
        await self._request("POST", "/posts", json=payload)

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        try:
            response = await self._client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            # Never include response bodies: upstream errors can echo headers or
            # contain sensitive operational details. Status is enough to debug.
            status = getattr(getattr(exc, "response", None), "status_code", "unavailable")
            raise MattermostError(
                f"Mattermost {method} {path} failed (HTTP {status})."
            ) from exc

    @staticmethod
    def _slug(value: str) -> str:
        return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value.lower())).strip("-")

    @staticmethod
    def _format_duration(duration) -> str:
        total_seconds = max(0, int(duration.total_seconds()))
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours}h {minutes}m {seconds}s"
